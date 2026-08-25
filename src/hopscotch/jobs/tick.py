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
from ..brief import brief_effect
from ..claims import MAX_ASSESSMENTS_PER_TICK, assess_pending
from ..pipeline import (
    MAX_NOTICES_PER_TICK, PipelineFailed, draft_and_send, process_inbox,
)
from ..idempotency import Ledger, escalation_effect, run_key_for
from ..schemas import DeadlineComputation, WorkerResult
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

    counts = {"scanned": 0, "escalated": 0, "suppressed": 0, "notices_sent": 0,
              "needs_intake": 0, "dead_lettered": 0, "errors": 0,
              "claims_assessed": 0, "claims_billable": 0, "notices_delivered": 0,
              "documents_read": 0, "documents_blocked": 0}
    drafted = 0

    with span("job.tick", day=today.isoformat(), run_key=run_key) as s:
        from ..gateway import Gateway
        from ..supervisor.resilience import CircuitOpen, call_worker

        # One gateway for the whole tick: the registry is read once, not per case.
        gw = Gateway()

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
                    # Firestore holds the fact; Memory Bank holds the narrative
                    # a future session needs. Best-effort on purpose -- a
                    # missing recollection must never fail a statutory check.
                    _remember(case.student_ref, comp, rung)
                    counts["escalated"] += 1

                    # Delegate: casework drafts, Gemma redacts, family writes,
                    # Chirp speaks. Bounded per tick so twelve simultaneous
                    # escalations do not become one burst of ~48 model calls.
                    if drafted < MAX_NOTICES_PER_TICK:
                        drafted += 1
                        try:
                            res = draft_and_send(case, comp, rung, gateway=gw)
                            counts["notices_sent"] += 1
                            log.info("notice for %s in %s (audio=%s)",
                                     res.student_ref, res.language,
                                     bool(res.audio_path))
                        except PipelineFailed as e:
                            # The escalation is claimed, so the warning is
                            # recorded -- but no notice went out. A human has
                            # to draft this one, and must be told.
                            log.warning("notice pipeline failed for %s: %s",
                                        case.student_ref, e)
                            store.dead_letter(
                                WorkerResult(agent="casework_agent", ok=False,
                                             error=str(e)[:300]),
                                student_ref=case.student_ref,
                                reason="escalation recorded but notice not generated",
                                run_key=run_key)
                            counts["dead_lettered"] += 1
                else:
                    counts["suppressed"] += 1
                # Firing a tight rung retires every looser one, so a late
                # discovery does not replay the whole ladder tick by tick.
                for retired in superseded_by(rung):
                    if retired not in case.escalations_sent:
                        case.escalations_sent.append(retired)

            store.upsert_case(case)

        # Intake first: a document dropped a minute ago should become a case
        # in this pass, not the next one.
        try:
            intake = process_inbox(store=store)
            counts["documents_read"] = intake["read"]
            counts["documents_blocked"] = intake["blocked"] + intake["failed"]
        except Exception as e:
            log.warning("intake pass skipped: %s: %s", type(e).__name__, str(e)[:160])

        # Deliver anything a human approved since the last tick. The fleet
        # never approves its own notices.
        try:
            from ..delivery import send_approved
            counts["notices_delivered"] = send_approved(store=store)
        except Exception as e:
            log.warning("delivery pass skipped: %s: %s", type(e).__name__, str(e)[:160])

        # Claim readiness on any session logged since the last tick. Bounded
        # for the same reason notices are: a model call per session, and a
        # district logs hundreds a week.
        try:
            n, ok = assess_pending(store=store, limit=MAX_ASSESSMENTS_PER_TICK)
            counts["claims_assessed"], counts["claims_billable"] = n, ok
        except Exception as e:
            log.warning("claim assessment skipped: %s: %s", type(e).__name__, str(e)[:160])

        # Once a day, the supervisor writes the coordinator's brief. Claimed
        # through the same ledger as everything else, so the other 23 ticks are
        # a no-op rather than 24 briefs.
        if ledger.claim(brief_effect(today), kind="daily_brief", run_key=run_key):
            try:
                from ..brief import generate, save
                brief = generate(today=today, store=store)
                save(brief)
                counts["brief"] = 1
                log.info("brief for %s: %s", today.isoformat(), brief.headline)
            except Exception as e:
                counts["brief"] = 0
                log.warning("brief generation failed for %s: %s: %s",
                            today.isoformat(), type(e).__name__, str(e)[:200])

        for k, v in counts.items():
            s.set_attribute(k, v)

    log.info("tick %s complete: %s", run_key, counts)
    return counts


def _remember(student_ref: str, comp: DeadlineComputation, rung: int) -> None:
    try:
        from ..memory import remember
        remember(
            student_ref,
            f"Escalated at T-{rung}: evaluation due {comp.due_on.isoformat()} "
            f"under {comp.rule_label}, {comp.days_remaining} days remaining. "
            f"{comp.explanation}",
            author="clock-agent",
        )
    except Exception as e:  # memory is an enhancement, never a dependency
        log.info("memory write skipped for %s: %s", student_ref, e)


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
