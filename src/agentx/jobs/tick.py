"""The scheduled tick. Cloud Scheduler -> Pub/Sub -> Cloud Run Job -> here.

Nobody is watching when this runs. That is the point: the fleet's job is to
notice a deadline approaching on a Tuesday in October and act on it.

Day 1 ships this as a heartbeat. Day 3 turns on the clock. The schedule itself
does not change, which is why ten days of unbroken trace history exists by the
time the demo is recorded.
"""
from __future__ import annotations

import logging
import sys
from datetime import date

from ..config import PROJECT_SLUG
from ..schemas import DeadlineComputation
from ..telemetry import span

log = logging.getLogger(PROJECT_SLUG)


def run_tick(today: date | None = None) -> dict:
    today = today or date.today()
    counts = {"scanned": 0, "escalated": 0, "dead_lettered": 0, "errors": 0}

    with span("job.tick", day=today.isoformat()) as s:
        from .. import store
        from ..agents import clock as clock_agent_mod
        from ..supervisor.resilience import CircuitOpen, call_worker

        for case in store.open_cases():
            counts["scanned"] += 1
            try:
                result, comp = call_worker(
                    "clock_agent",
                    lambda attempt, c=case: clock_agent_mod.recompute(
                        c, today=today
                    ).model_dump(mode="json"),
                    DeadlineComputation,
                    student_ref=case.student_ref,
                )
            except CircuitOpen as e:
                log.warning("circuit open, skipping: %s", e)
                counts["errors"] += 1
                continue

            if not result.ok or comp is None:
                store.dead_letter(result, student_ref=case.student_ref,
                                  reason="clock recompute failed")
                counts["dead_lettered"] += 1
                continue

            case.deadline = comp
            rung = clock_agent_mod.pending_escalation(case, comp)
            if rung is not None:
                case.escalations_sent.append(rung)
                store.audit("escalation_fired", student_ref=case.student_ref,
                            rung=rung, due_on=comp.due_on.isoformat(),
                            days_remaining=comp.days_remaining)
                counts["escalated"] += 1
                # TODO(day-4): route to casework_agent through the supervisor

            store.upsert_case(case)

        for k, v in counts.items():
            s.set_attribute(k, v)

    log.info("tick complete: %s", counts)
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
