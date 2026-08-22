"""The scheduled tick. Cloud Scheduler -> Cloud Run Job -> here.

Nobody is watching when this runs. That is the point: the fleet's job is to
notice a deadline approaching on a Tuesday in October and act on it.

Day 1 ships this as a heartbeat. Day 3 turns on the clock. The schedule itself
does not change, which is why ten days of unbroken trace history exists by the
time the demo is recorded.

Every side effect here is claimed through a ledger before it fires, so this is
safe to run twice -- see idempotency.py for why that is a requirement and not
a nicety.
"""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timezone

from ..config import PROJECT_SLUG
from ..deadlines import (
    ClockCannotStart, pending_escalation, recompute, superseded_by,
)
from ..idempotency import Ledger, escalation_effect, run_key_for
from ..schemas import DeadlineComputation
from ..telemetry import span

log = logging.getLogger(PROJECT_SLUG)


def run_tick(
    *,
    today: date | None = None,
    now: datetime | None = None,
    ledger: Ledger | None = None,
    store=None,
) -> dict:
    """One pass over every open case.

    `store` and `ledger` are injectable so the idempotency guarantee can be
    tested without Firestore. Defaults are the real thing.
    """
    today = today or date.today()
    now = now or datetime.now(timezone.utc)
    run_key = run_key_for(now)

    if store is None:
        from .. import store as store
    if ledger is None:
        from ..store import FirestoreLedger
        ledger = FirestoreLedger()

    counts = {"scanned": 0, "escalated": 0, "suppressed": 0,
              "needs_intake": 0, "dead_lettered": 0, "errors": 0}

    with span("job.tick", day=today.isoformat(), run_key=run_key) as s:
        from ..supervisor.resilience import CircuitOpen, call_worker

        for case in store.open_cases():
            counts["scanned"] += 1
            # Not an error and not retryable: an illegible signature date means
            # a human has to read the form. Counted, not dead-lettered, so it
            # does not refile itself every hour for the life of the case.
            if case.consent is not None and case.consent.consent_signed_on is None:
                counts["needs_intake"] += 1
                continue
            try:
                result, comp = call_worker(
                    "clock_agent",
                    lambda attempt, c=case: recompute(
                        c, today=today
                    ).model_dump(mode="json"),
                    DeadlineComputation,
                    student_ref=case.student_ref,
                )
            except ClockCannotStart:
                counts["needs_intake"] += 1
                continue
            except CircuitOpen as e:
                log.warning("circuit open, skipping: %s", e)
                counts["errors"] += 1
                continue

            if not result.ok or comp is None:
                store.dead_letter(result, student_ref=case.student_ref,
                                  reason="clock recompute failed", run_key=run_key)
                counts["dead_lettered"] += 1
                continue

            case.deadline = comp
            rung = pending_escalation(case, comp)
            if rung is not None:
                eid = escalation_effect(case.student_ref, rung)
                # Claim BEFORE the effect, not after. A crash between the claim
                # and the send costs one missed notice, which the coordinator
                # sees in the dashboard. A crash between the send and the claim
                # would spam a family on every tick for the rest of the case.
                if ledger.claim(eid, student_ref=case.student_ref, rung=rung,
                                run_key=run_key):
                    store.audit("escalation_fired", effect_id=eid,
                                student_ref=case.student_ref, rung=rung,
                                run_key=run_key,
                                due_on=comp.due_on.isoformat(),
                                days_remaining=comp.days_remaining)
                    counts["escalated"] += 1
                    # TODO(day-4): route to casework_agent through the supervisor
                else:
                    counts["suppressed"] += 1
                # Firing a tight rung retires every looser one, so a late
                # discovery does not replay the whole ladder tick by tick.
                for retired in superseded_by(rung):
                    if retired not in case.escalations_sent:
                        case.escalations_sent.append(retired)

            store.upsert_case(case)

        for k, v in counts.items():
            s.set_attribute(k, v)

    log.info("tick %s complete: %s", run_key, counts)
    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        run_tick()
    except Exception:
        log.exception("tick failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
