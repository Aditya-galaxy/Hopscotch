"""Delivery: how a notice actually reaches a family.

The design constraint that matters is not technical. A system that autonomously
mails legal notices to families about their children is not something a district
will accept, and it should not be. So delivery is a two-step:

    the fleet DRAFTS and queues        (unattended)
    a named human APPROVES             (never the agent)
    the driver SENDS                   (recorded, idempotent)

Nothing leaves without `approved_by` set to a real person. That is enforced in
send(), not in the UI, so a future caller cannot skip it.

Drivers are swappable because districts differ: some run their own SMTP, some
use a parent portal, some still print and post. The abstraction is deliberately
thin -- one method, and a record of what happened.
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from enum import Enum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from .idempotency import effect_id
from .telemetry import span

OUTBOX = "outbox"


class Status(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    REJECTED = "rejected"
    FAILED = "failed"


class NotApproved(PermissionError):
    """Someone tried to send an unapproved notice. This is a bug, not a state."""


class Outbound(BaseModel):
    """A notice waiting on a human."""
    id: str
    student_ref: str
    notice_type: str
    language: str = "en-US"
    subject: str
    body: str
    audio_path: str | None = None
    recipient: str = Field(
        default="", description="Empty in synthetic mode; no real family exists")
    status: Status = Status.PENDING_APPROVAL
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_by: str = ""
    approved_at: str = ""
    sent_at: str = ""
    error: str = ""


class Driver(Protocol):
    name: str

    def send(self, item: Outbound) -> str:
        """Deliver and return a provider reference. Raise to fail the send."""


@dataclass
class FileDriver:
    """Writes to disk. The default, and correct for synthetic data.

    A district running this against invented students must not be one
    misconfiguration away from mailing strangers.
    """
    name: str = "file"
    root: Path = Path("data/outbox")

    def send(self, item: Outbound) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        p = self.root / f"{item.id}.txt"
        p.write_text(
            f"To: {item.recipient or '(synthetic — no recipient)'}\n"
            f"Subject: {item.subject}\n"
            f"Language: {item.language}\n"
            f"Approved by: {item.approved_by}\n\n{item.body}\n")
        return str(p)


def _smtp_password() -> str | None:
    """Read the SMTP password from a mounted secret, falling back to env.

    Cloud Run can mount a Secret Manager version as a FILE, which is preferable
    to an environment variable: env vars are visible in the service description,
    leak into crash dumps and subprocess environments, and are trivially printed
    by any code that logs os.environ. A mounted file is read once, at the moment
    it is needed.

    The env fallback exists for local development only, and this function is the
    single place either is read -- so the value never lands in a log line.
    """
    path = os.environ.get("SMTP_PASSWORD_FILE")
    if path:
        try:
            return Path(path).read_text().strip() or None
        except OSError:
            return None
    return os.environ.get("SMTP_PASSWORD") or None


@dataclass
class SmtpDriver:
    """Real send. Configured, never guessed -- a missing host raises."""
    name: str = "smtp"

    def send(self, item: Outbound) -> str:
        host = os.environ.get("SMTP_HOST")
        if not host:
            raise RuntimeError("SMTP_HOST unset; refusing to guess a mail route")
        if not item.recipient:
            raise RuntimeError(f"{item.id} has no recipient")

        msg = EmailMessage()
        msg["Subject"] = item.subject
        msg["From"] = os.environ.get("SMTP_FROM", "no-reply@district.example")
        msg["To"] = item.recipient
        msg.set_content(item.body)

        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            user, pw = os.environ.get("SMTP_USER"), _smtp_password()
            if user and pw:
                s.login(user, pw)
            s.send_message(msg)
        return f"smtp:{host}:{item.recipient}"


def driver() -> Driver:
    """File by default. Real delivery is opt-in, never the fallback."""
    return SmtpDriver() if os.environ.get("DELIVERY_DRIVER") == "smtp" else FileDriver()


def queue(*, student_ref: str, notice_type: str, subject: str, body: str,
          language: str = "en-US", audio_path: str | None = None,
          recipient: str = "", store=None) -> Outbound:
    """Draft into the outbox. Idempotent per student, notice type and day."""
    from . import store as default_store
    store = store or default_store

    item = Outbound(
        id=effect_id("outbound", student_ref, notice_type,
                     datetime.now(timezone.utc).date().isoformat()),
        student_ref=student_ref, notice_type=notice_type, subject=subject,
        body=body, language=language, audio_path=audio_path, recipient=recipient)
    with span("delivery.queue", student_ref=student_ref, notice_type=notice_type):
        store.upsert_outbound(item)
    return item


def approve(item_id: str, *, approved_by: str, store=None) -> Outbound:
    """A named human takes responsibility. Agents cannot call this."""
    from . import store as default_store
    store = store or default_store

    if not approved_by.strip():
        raise NotApproved("approval requires a named person")
    item = store.get_outbound(item_id)
    if item is None:
        raise KeyError(item_id)
    item.status = Status.APPROVED
    item.approved_by = approved_by
    item.approved_at = datetime.now(timezone.utc).isoformat()
    store.upsert_outbound(item)
    return item


def reject(item_id: str, *, rejected_by: str, store=None) -> Outbound:
    from . import store as default_store
    store = store or default_store
    item = store.get_outbound(item_id)
    if item is None:
        raise KeyError(item_id)
    item.status = Status.REJECTED
    item.approved_by = rejected_by
    store.upsert_outbound(item)
    return item


def send(item: Outbound, *, drv: Driver | None = None, store=None) -> Outbound:
    """Deliver an approved notice. Refuses anything else."""
    from . import store as default_store
    store = store or default_store
    drv = drv or driver()

    if item.status is not Status.APPROVED or not item.approved_by:
        raise NotApproved(
            f"{item.id} is {item.status.value}; only an approved notice with a "
            "named approver may be sent")

    with span("delivery.send", driver=drv.name, student_ref=item.student_ref) as s:
        try:
            ref = drv.send(item)
        except Exception as e:
            item.status = Status.FAILED
            item.error = f"{type(e).__name__}: {e}"[:300]
            store.upsert_outbound(item)
            s.set_attribute("ok", False)
            raise
        item.status = Status.SENT
        item.sent_at = datetime.now(timezone.utc).isoformat()
        item.error = ref[:300]
        store.upsert_outbound(item)
        s.set_attribute("ok", True)
        return item


def send_approved(*, limit: int = 20, store=None, drv: Driver | None = None) -> int:
    """Send everything a human has approved since the last run."""
    from . import store as default_store
    store = store or default_store
    sent = 0
    for item in store.approved_outbound(limit=limit):
        try:
            send(item, drv=drv, store=store)
            sent += 1
        except Exception:
            continue  # recorded as FAILED on the item; the queue keeps moving
    return sent
