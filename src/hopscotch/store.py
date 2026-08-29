"""Firestore case store. The only module that knows the persistence shape."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

from google.api_core import exceptions as gexc
from functools import lru_cache

from google.cloud import firestore

from .config import settings
from .idempotency import deadletter_effect
from .schemas import Case, WorkerResult


def _database() -> str | None:
    """Firestore's default database must be passed as None, not "(default)".

    Newer google-cloud-firestore percent-encodes an explicit database id into
    the resource path, so the literal string arrives as %28default%29 and every
    call fails with InvalidArgument. Passing None uses the default database and
    works on every version.
    """
    db = (settings.firestore_db or "").strip()
    return None if db in ("", "(default)", "default") else db


def client_kwargs() -> dict:
    """Arguments for a Firestore client, with `database` OMITTED by default.

    One place builds a client, so credentials and database resolution cannot
    drift apart across modules.

    Historical note, because the comment here used to blame the wrong thing:
    the `Invalid database id %28default%29` outage of 25 Aug was NOT caused by
    how the database argument was passed. Every form failed identically --
    "(default)", None, and omitting it. The cause was google-api-core 2.35.0,
    now pinned below that in requirements.txt. This helper is kept because
    single-sourcing client construction is worth having regardless.
    """
    kwargs: dict = {"project": settings.project_id or None}
    db = _database()
    if db:
        kwargs["database"] = db
    return kwargs


@lru_cache(maxsize=4)
def _client_for(key: tuple) -> firestore.Client:
    return firestore.Client(**dict(key))


def _client() -> firestore.Client:
    """The Firestore client, reused.

    This used to build a NEW client on every call, and every store function
    calls it -- so rendering one dashboard page constructed dozens of clients,
    each paying gRPC channel setup and credential resolution. That was 26
    seconds of a 30-second page load; the queries themselves are fast.

    Cached on the connection kwargs rather than globally, so a test or a process
    that changes project or database still gets its own client instead of
    silently reusing one pointed at the wrong place. The client is thread-safe
    and intended to be long-lived.
    """
    return _client_for(tuple(sorted(client_kwargs().items())))


def upsert_case(case: Case) -> None:
    case.updated_at = datetime.now(timezone.utc)
    _client().collection(settings.cases_collection).document(
        case.student_ref
    ).set(case.model_dump(mode="json"), merge=True)


def get_case(student_ref: str) -> Case | None:
    snap = _client().collection(settings.cases_collection).document(student_ref).get()
    return Case.model_validate(snap.to_dict()) if snap.exists else None


def open_cases() -> Iterator[Case]:
    q = _client().collection(settings.cases_collection).where(
        filter=firestore.FieldFilter("stage", "!=", "closed")
    )
    for snap in q.stream():
        yield Case.model_validate(snap.to_dict())


class FirestoreLedger:
    """Idempotency ledger backed by document-id uniqueness.

    `create()` fails if the document exists, and that failure IS the dedupe --
    it is atomic at the Firestore level, so two concurrent tick executions
    cannot both win the same claim. A read-then-write would race.
    """

    def __init__(self, collection: str = "effects") -> None:
        self._collection = collection

    def claim(self, eid: str, **meta) -> bool:
        ref = _client().collection(self._collection).document(eid)
        try:
            ref.create({"at": datetime.now(timezone.utc).isoformat(), **meta})
            return True
        except gexc.AlreadyExists:
            return False


def audit(event: str, *, effect_id: str, student_ref: str | None = None, **fields) -> bool:
    """Append-only. Returns False if this exact effect was already recorded.

    Uses create(), not set(). A deterministic document id gives idempotency
    either way, but set() would let a later write OVERWRITE an existing audit
    row -- and a mutable audit trail is not an audit trail. A district lawyer
    reconstructs decisions from this collection; if it can be rewritten, it
    proves nothing.

    AlreadyExists is the idempotency signal, not an error.
    """
    ref = _client().collection(settings.audit_collection).document(effect_id)
    try:
        ref.create({
            "event": event,
            "student_ref": student_ref,
            "at": datetime.now(timezone.utc).isoformat(),
            **fields,
        })
        return True
    except gexc.AlreadyExists:
        return False


def deliveries_for(student_ref: str) -> list[dict]:
    """Service sessions logged against a case."""
    q = (_client().collection("deliveries")
         .where(filter=firestore.FieldFilter("student_ref", "==", student_ref)))
    return [d.to_dict() for d in q.stream()]


def open_deliveries(limit: int = 200) -> list[dict]:
    """Sessions not yet assessed for claim readiness."""
    q = (_client().collection("deliveries")
         .where(filter=firestore.FieldFilter("assessed", "==", False)).limit(limit))
    return [d.to_dict() | {"_id": d.id} for d in q.stream()]


def save_readiness(readiness, *, delivery_id: str) -> None:
    """Record the verdict and mark the session assessed, so a replay is a no-op."""
    db = _client()
    db.collection("claim_readiness").document(delivery_id).set(
        readiness.model_dump(mode="json"))
    db.collection("deliveries").document(delivery_id).update({"assessed": True})


def readiness_summary() -> dict:
    """What the coordinator needs: billable, blocked, and money left behind."""
    rows = [d.to_dict() for d in
            _client().collection("claim_readiness").limit(500).stream()]
    billable = sum(1 for r in rows if r.get("billable"))
    blocked, unclaimed_units = [], 0
    for r in rows:
        for c in r.get("checks", []):
            if c.get("passed"):
                continue
            if c.get("blocking"):
                blocked.append({"student_ref": r.get("student_ref"),
                                "requirement": c.get("requirement"),
                                "detail": c.get("detail", "")})
            elif "under-billed" in (c.get("detail") or ""):
                unclaimed_units += 1
    return {"assessed": len(rows), "billable": billable,
            "blocked": blocked, "underbilled_sessions": unclaimed_units}


def apply_correction(student_ref: str, correction) -> None:
    """Record a human override and re-open the clock for it.

    Escalations already sent are cleared so a corrected deadline re-evaluates
    from scratch -- otherwise a case corrected from 'overdue' to 'due in three
    weeks' would stay silent because its rungs were already spent.
    """
    from .idempotency import effect_id

    case = get_case(student_ref)
    if case is None:
        raise KeyError(student_ref)
    case.corrections.append(correction)
    case.escalations_sent = []
    upsert_case(case)

    audit("case_corrected",
          effect_id=effect_id("correction", student_ref, correction.field,
                              correction.at.isoformat()),
          student_ref=student_ref, field=correction.field,
          value=correction.value.isoformat(), reason=correction.reason,
          by=correction.by, computed_was=correction.computed_was)


# --- inbox: documents dropped by a human, processed by the fleet -------------

def queue_document(*, text: str, source: str, dropped_by: str) -> str:
    """Accept a consent document for intake.

    The dashboard has no model access by design, so it does not extract here --
    it records the document and the tick picks it up. That keeps the coordinator
    surface unable to call Vertex even if it is compromised, and it matches how
    the rest of the system works: a human drops something, the fleet acts on it
    unattended.
    """
    from .idempotency import effect_id

    doc_id = effect_id("inbox", source, text[:2000])
    _client().collection("inbox").document(doc_id).set({
        "text": text, "source": source, "dropped_by": dropped_by,
        "status": "pending",
        "at": datetime.now(timezone.utc).isoformat(),
    })
    return doc_id


def pending_documents(limit: int = 10) -> list[dict]:
    q = (_client().collection("inbox")
         .where(filter=firestore.FieldFilter("status", "==", "pending")).limit(limit))
    return [d.to_dict() | {"_id": d.id} for d in q.stream()]


def resolve_document(doc_id: str, *, status: str, detail: str = "",
                     student_ref: str = "") -> None:
    _client().collection("inbox").document(doc_id).update({
        "status": status, "detail": detail[:400], "student_ref": student_ref,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    })


def inbox_recent(limit: int = 12) -> list[dict]:
    rows = [d.to_dict() | {"_id": d.id}
            for d in _client().collection("inbox").limit(60).stream()]
    return sorted(rows, key=lambda r: r.get("at", ""), reverse=True)[:limit]


# --- outbox -----------------------------------------------------------------

def upsert_outbound(item) -> None:
    _client().collection("outbox").document(item.id).set(item.model_dump(mode="json"))


def get_outbound(item_id: str):
    from .delivery import Outbound
    snap = _client().collection("outbox").document(item_id).get()
    return Outbound.model_validate(snap.to_dict()) if snap.exists else None


def pending_outbound(limit: int = 50) -> list:
    from .delivery import Outbound
    q = (_client().collection("outbox")
         .where(filter=firestore.FieldFilter("status", "==", "pending_approval"))
         .limit(limit))
    return [Outbound.model_validate(d.to_dict()) for d in q.stream()]


def approved_outbound(limit: int = 20) -> list:
    from .delivery import Outbound
    q = (_client().collection("outbox")
         .where(filter=firestore.FieldFilter("status", "==", "approved")).limit(limit))
    return [Outbound.model_validate(d.to_dict()) for d in q.stream()]


def outbox_summary() -> dict:
    rows = [d.to_dict() for d in _client().collection("outbox").limit(500).stream()]
    by = {}
    for r in rows:
        by[r.get("status", "?")] = by.get(r.get("status", "?"), 0) + 1
    return {"total": len(rows), "by_status": by}


def dead_letter(result: WorkerResult, *, student_ref: str, reason: str,
                run_key: str) -> None:
    """Where work goes when the fleet cannot finish it. A human queue, not /dev/null."""
    eid = deadletter_effect(student_ref, result.agent, run_key)
    _client().collection(settings.deadletter_collection).document(eid).set(
        {
            "student_ref": student_ref,
            "agent": result.agent,
            "attempts": result.attempt,
            "error": result.error,
            "reason": reason,
            "run_key": run_key,
            "at": datetime.now(timezone.utc).isoformat(),
            "needs_human": True,
        }
    )
