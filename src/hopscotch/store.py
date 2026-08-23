"""Firestore case store. The only module that knows the persistence shape."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

from google.api_core import exceptions as gexc
from google.cloud import firestore

from .config import settings
from .idempotency import deadletter_effect
from .schemas import Case, WorkerResult


def _client() -> firestore.Client:
    return firestore.Client(
        project=settings.project_id or None, database=settings.firestore_db
    )


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


def audit(event: str, *, effect_id: str, student_ref: str | None = None, **fields) -> None:
    """Append-only, with a deterministic id so a replay overwrites rather than duplicates.

    A district lawyer reconstructs decisions from this collection. An audit
    trail that double-writes on retry is worse than none -- it makes the record
    look falsified precisely when someone is checking it.
    """
    _client().collection(settings.audit_collection).document(effect_id).set(
        {
            "event": event,
            "student_ref": student_ref,
            "at": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
    )


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
