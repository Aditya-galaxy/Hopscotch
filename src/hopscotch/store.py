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
