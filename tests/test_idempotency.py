"""The tick will run ~240 times unattended. It must be safe to run twice.

These tests exist because "we retry on failure" and "we never double-send" are
in tension, and the only way to have both is per-effect claims. If someone
later replaces the ledger with a read-then-write, test_two_ticks_same_hour
fails and says why.
"""
from datetime import date, datetime, timezone

import pytest

from hopscotch.idempotency import (
    InMemoryLedger, deadletter_effect, escalation_effect, run_key_for,
)
from hopscotch.jobs.tick import run_tick
from hopscotch.schemas import Case, CaseStage, ConsentEvent


class FakeStore:
    """Records every write so a test can count them."""

    def __init__(self, cases):
        self._cases = {c.student_ref: c for c in cases}
        self.audits: list[tuple[str, str]] = []
        self.dead_letters: list[str] = []
        self.upserts = 0

    def open_cases(self):
        return list(self._cases.values())

    def upsert_case(self, case):
        self._cases[case.student_ref] = case
        self.upserts += 1

    def audit(self, event, *, effect_id, student_ref=None, **fields):
        self.audits.append((effect_id, event))

    def dead_letter(self, result, *, student_ref, reason, run_key):
        self.dead_letters.append(deadletter_effect(student_ref, result.agent, run_key))


def a_case(ref="stu_0001", signed=date(2026, 9, 1)) -> Case:
    return Case(
        student_ref=ref, school_code="EL-004", jurisdiction="US_FEDERAL",
        stage=CaseStage.CONSENT_RECEIVED,
        consent=ConsentEvent(
            student_ref=ref, school_code="EL-004", jurisdiction="US_FEDERAL",
            consent_signed_on=signed, received_on=signed,
            confidence=0.95, source_document="consent.pdf",
        ),
    )


# --- key derivation ----------------------------------------------------------

def test_run_key_buckets_by_hour():
    a = datetime(2026, 8, 21, 14, 3, tzinfo=timezone.utc)
    b = datetime(2026, 8, 21, 14, 59, tzinfo=timezone.utc)
    c = datetime(2026, 8, 21, 15, 0, tzinfo=timezone.utc)
    assert run_key_for(a) == run_key_for(b)
    assert run_key_for(a) != run_key_for(c)


def test_escalation_effect_is_independent_of_run():
    # A T-7 warning happens once in a case's life, not once per tick. If this
    # ever starts varying by run key, escalations will re-fire hourly.
    assert escalation_effect("stu_1", 7) == escalation_effect("stu_1", 7)
    assert escalation_effect("stu_1", 7) != escalation_effect("stu_1", 14)
    assert escalation_effect("stu_1", 7) != escalation_effect("stu_2", 7)


def test_deadletter_effect_is_scoped_per_run():
    # A case that keeps failing should keep surfacing to the human queue.
    assert (deadletter_effect("stu_1", "clock_agent", "tick-A")
            != deadletter_effect("stu_1", "clock_agent", "tick-B"))


# --- the actual guarantee ----------------------------------------------------

@pytest.fixture
def near_deadline():
    """One case sitting at T-6, so an escalation is due."""
    return FakeStore([a_case()]), date(2026, 10, 25)


def test_single_tick_escalates_once(near_deadline):
    store, today = near_deadline
    counts = run_tick(today=today, ledger=InMemoryLedger(), store=store)
    assert counts["escalated"] == 1
    assert counts["suppressed"] == 0
    assert len(store.audits) == 1


def test_two_ticks_same_hour_escalate_once(near_deadline):
    """Cloud Run retried the job, or Scheduler fired at-least-once twice."""
    store, today = near_deadline
    ledger = InMemoryLedger()
    now = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)

    first = run_tick(today=today, now=now, ledger=ledger, store=store)
    second = run_tick(today=today, now=now, ledger=ledger, store=store)

    assert first["escalated"] == 1
    assert second["escalated"] == 0
    assert len(store.audits) == 1, "audit trail double-wrote on replay"


def test_ledger_suppresses_when_case_state_was_lost():
    """The crash the ledger actually exists for.

    The job sent the notice, then died before upsert_case persisted
    escalations_sent. Case state says "nothing sent yet". Without a durable
    per-effect claim the family gets the same notice on every tick, forever.
    """
    store = FakeStore([a_case()])
    ledger = InMemoryLedger()
    today = date(2026, 10, 25)

    run_tick(today=today, ledger=ledger, store=store)
    store._cases["stu_0001"].escalations_sent.clear()   # the write that never landed

    replay = run_tick(today=today, ledger=ledger, store=store)

    assert replay["escalated"] == 0
    assert replay["suppressed"] == 1, "ledger did not catch the lost-state replay"
    assert len(store.audits) == 1


def test_ticks_across_hours_still_escalate_once(near_deadline):
    """The real shape of the bug: 24 ticks a day, same rung still pending."""
    store, today = near_deadline
    ledger = InMemoryLedger()
    for hour in range(9, 21):
        run_tick(today=today,
                 now=datetime(2026, 10, 25, hour, tzinfo=timezone.utc),
                 ledger=ledger, store=store)
    assert len(store.audits) == 1, f"{len(store.audits)} notices for one rung"


def test_audit_ids_are_stable_across_replays(near_deadline):
    store, today = near_deadline
    ledger = InMemoryLedger()
    run_tick(today=today, ledger=ledger, store=store)
    eid, event = store.audits[0]
    assert event == "escalation_fired"
    assert eid == escalation_effect("stu_0001", 7)  # tightest applicable at T-6


def test_later_rung_fires_as_deadline_closes(near_deadline):
    """Suppression must not be so aggressive that T-7 never fires after T-14."""
    store, _ = near_deadline
    ledger = InMemoryLedger()
    run_tick(today=date(2026, 10, 19), ledger=ledger, store=store)   # T-12 -> 14
    run_tick(today=date(2026, 10, 27), ledger=ledger, store=store)   # T-4  -> 7
    rungs = sorted(store._cases["stu_0001"].escalations_sent)
    assert rungs == [7, 14]
    assert len(store.audits) == 2


def test_late_discovery_sends_one_notice_not_three():
    """A case first seen at T-1 gets the 2-day notice only, never 14 then 7 then 2."""
    store = FakeStore([a_case()])
    ledger = InMemoryLedger()
    run_tick(today=date(2026, 10, 30), ledger=ledger, store=store)   # T-1
    assert len(store.audits) == 1
    assert store.audits[0][0] == escalation_effect("stu_0001", 2)
    assert sorted(store._cases["stu_0001"].escalations_sent) == [2, 7, 14]


# --- transient vs permanent --------------------------------------------------

def test_permanent_failures_are_not_retried():
    """Classified by type, not by message.

    An earlier version substring-matched, and ArmorUnavailable -- which means
    "no template configured" -- was retried three times because its class name
    contains "unavailable".
    """
    from hopscotch.armor import ArmorUnavailable
    from hopscotch.genai import CredentialsMissing
    from hopscotch.supervisor.resilience import is_transient

    for e in (ArmorUnavailable("no template"), CredentialsMissing("no key"),
              NotImplementedError("not wired"), ValueError("bad shape")):
        assert not is_transient(e), f"{type(e).__name__} must not be retried"


def test_rate_limits_are_retried():
    from hopscotch.supervisor.resilience import is_transient

    class ClientError(Exception):
        pass

    assert is_transient(ClientError("429 RESOURCE_EXHAUSTED"))
    assert is_transient(ClientError("503 Service Unavailable"))
    assert is_transient(TimeoutError("timed out"))


def test_backoff_retries_then_succeeds():
    from hopscotch.supervisor.resilience import with_backoff

    slept: list[float] = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "ok"

    assert with_backoff(flaky, sleep=slept.append) == "ok"
    assert calls["n"] == 3
    assert len(slept) == 2
    assert slept[1] > slept[0], "backoff is not increasing"


def test_backoff_gives_up_and_reraises():
    from hopscotch.supervisor.resilience import with_backoff

    def always():
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    with pytest.raises(RuntimeError):
        with_backoff(always, attempts=2, sleep=lambda _: None)


# --- illegible consent dates -------------------------------------------------

def test_illegible_date_does_not_start_the_clock():
    """An unknown signature date is a real, common state, not an error.

    Roughly a fifth of the corpus has an illegible signature. Forcing a date
    into the schema would make the agent choose between inventing one and
    failing -- and a statutory clock started from a guessed date is worse than
    one a human is asked to confirm.
    """
    from hopscotch.deadlines import ClockCannotStart, recompute

    case = a_case()
    case.consent.consent_signed_on = None
    case.consent.received_on = None
    with pytest.raises(ClockCannotStart):
        recompute(case, today=date(2026, 10, 25))


def test_tick_counts_illegible_cases_instead_of_dead_lettering_them():
    """Dead-lettering would refile the same case every hour, forever.

    Over 240 unattended ticks that is 240 rows in a human queue for one form
    that needs reading once.
    """
    case = a_case()
    case.consent.consent_signed_on = None
    case.consent.received_on = None
    store = FakeStore([case])

    counts = run_tick(today=date(2026, 10, 25), ledger=InMemoryLedger(), store=store)

    assert counts["needs_intake"] == 1
    assert counts["dead_lettered"] == 0
    assert counts["errors"] == 0
    assert store.dead_letters == []


def test_a_case_the_fleet_can_now_compute_stops_being_needs_intake():
    """The tick must not carry its own copy of the clock rule.

    A form whose receipt date is legible but whose signature is not can be
    computed -- and the statute keys off receipt anyway. The tick used to
    pre-check the signature and skip, so such a case sat in needs-intake
    forever because nothing ever asked recompute() again.
    """
    from hopscotch.deadlines import recompute

    case = a_case()
    case.consent.consent_signed_on = None
    case.consent.received_on = date(2026, 9, 10)
    out = recompute(case, today=date(2026, 10, 1))
    assert out.clock_started_on == date(2026, 9, 10)
