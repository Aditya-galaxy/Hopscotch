"""Idempotency for a job that will absolutely run twice.

An hourly Cloud Run Job across ten days is ~240 executions. Cloud Scheduler is
at-least-once, Cloud Run Jobs retry on failure, and a crash between "notice was
sent" and "case was saved" is not hypothetical -- over 240 runs it is expected.

The wrong fix is refusing to re-run. A tick that failed halfway MUST be safe to
retry, or a transient Firestore blip strands a case until someone notices.

So the guarantee is per-effect, not per-run: every side effect derives a
deterministic id from what it *is*, claims that id once, and becomes a no-op
forever after. Two scopes matter and they are different:

  escalation_effect()  -- once EVER for a given student and rung. A T-7 warning
                          is not a per-tick event; it is a thing that happens
                          one time in the life of a case.
  run_key_for()        -- once per logical hour, for the tick's own bookkeeping.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Protocol


def run_key_for(now: datetime | None = None) -> str:
    """Logical tick period. Two firings in the same hour share a key."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).strftime("tick-%Y%m%dT%H")


def effect_id(*parts: object) -> str:
    """Stable id for one side effect. Same inputs, same id, forever."""
    joined = "|".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def escalation_effect(student_ref: str, rung: int) -> str:
    """Deliberately excludes the run key -- this fires once in a case's life."""
    return effect_id("escalation", student_ref, rung)


def deadletter_effect(student_ref: str, agent: str, run_key: str) -> str:
    """Scoped to the run: a case that keeps failing should keep surfacing."""
    return effect_id("deadletter", student_ref, agent, run_key)


class Ledger(Protocol):
    def claim(self, eid: str, **meta) -> bool:
        """True if this caller won the claim; False if the effect already happened."""


class InMemoryLedger:
    """For tests, and for a local `make tick` with no Firestore credentials."""

    def __init__(self) -> None:
        self.claimed: dict[str, dict] = {}

    def claim(self, eid: str, **meta) -> bool:
        if eid in self.claimed:
            return False
        self.claimed[eid] = meta
        return True
