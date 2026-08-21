"""Firestore case store. The only module that knows the persistence shape."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

from google.cloud import firestore

from .config import settings
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


def audit(event: str, *, student_ref: str | None = None, **fields) -> None:
    """Append-only. A district lawyer reconstructs decisions from this."""
    _client().collection(settings.audit_collection).add(
        {
            "event": event,
            "student_ref": student_ref,
            "at": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
    )


def dead_letter(result: WorkerResult, *, student_ref: str, reason: str) -> None:
    """Where work goes when the fleet cannot finish it. A human queue, not /dev/null."""
    _client().collection(settings.deadletter_collection).add(
        {
            "student_ref": student_ref,
            "agent": result.agent,
            "attempts": result.attempt,
            "error": result.error,
            "reason": reason,
            "at": datetime.now(timezone.utc).isoformat(),
            "needs_human": True,
        }
    )
