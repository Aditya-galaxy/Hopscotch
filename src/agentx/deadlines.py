"""The clock. Pure functions -- no cloud, no model, fully testable.

This is the domain heart of the system and the one place a wrong answer has
legal consequences, so it is deliberately not delegated to an LLM. clock-agent
calls into this; it does not reason about dates itself.
"""
from __future__ import annotations

from datetime import date, timedelta

from .config import ESCALATION_LADDER
from .jurisdictions import JURISDICTIONS, RuleType, SchoolCalendar, demo_calendar
from .schemas import Case, DeadlineComputation

_US_FIXED_HOLIDAYS = {(1, 1), (7, 4), (11, 11), (12, 25)}


def _is_business_day(d: date) -> bool:
    return d.weekday() < 5 and (d.month, d.day) not in _US_FIXED_HOLIDAYS


def _break_runs(cal: SchoolCalendar, start: date, end: date) -> list[tuple[date, int]]:
    """Consecutive runs of non-instructional weekdays, as (first_day, length).

    A weekend inside a break is transparent: it neither adds to the run's
    length nor ends it. Winter break is one break that happens to span a
    Saturday, not two five-day breaks -- and under a "pauses for breaks longer
    than five days" rule that distinction decides whether the clock moves.
    Only a real instructional day closes a run.
    """
    runs: list[tuple[date, int]] = []
    cur_start: date | None = None
    length = 0
    d = start
    while d <= end:
        if cal.is_school_day(d):
            if cur_start is not None:
                runs.append((cur_start, length))
                cur_start, length = None, 0
        elif d.weekday() < 5:
            if cur_start is None:
                cur_start, length = d, 0
            length += 1
        d += timedelta(days=1)
    if cur_start is not None:
        runs.append((cur_start, length))
    return runs


def compute_deadline(
    *,
    student_ref: str,
    jurisdiction_key: str,
    clock_started_on: date,
    calendar: SchoolCalendar,
    today: date | None = None,
) -> DeadlineComputation:
    """Walk the calendar forward under the jurisdiction's counting rule."""
    today = today or date.today()
    j = JURISDICTIONS[jurisdiction_key]
    excluded = 0

    if j.rule is RuleType.CALENDAR_DAYS:
        due = clock_started_on + timedelta(days=j.count)
        if j.exclude_breaks_longer_than is not None:
            # Long breaks push the due date out; short ones do not. Pushing the
            # date can pull a NEW break into the window, so iterate to a fixed
            # point rather than scanning the original window once.
            counted: set[date] = set()
            while True:
                added = 0
                for run_start, length in _break_runs(calendar, clock_started_on, due):
                    if length > j.exclude_breaks_longer_than and run_start not in counted:
                        counted.add(run_start)
                        due += timedelta(days=length)
                        added += length
                excluded += added
                if added == 0:
                    break
        detail = f"{j.count} calendar days from {clock_started_on.isoformat()}"

    elif j.rule is RuleType.SCHOOL_DAYS:
        counted, cursor = 0, clock_started_on
        while counted < j.count:
            cursor += timedelta(days=1)
            if calendar.is_school_day(cursor):
                counted += 1
            else:
                excluded += 1
        due = cursor
        detail = f"{j.count} school days on the {calendar.district} calendar"

    else:  # BUSINESS_DAYS
        counted, cursor = 0, clock_started_on
        while counted < j.count:
            cursor += timedelta(days=1)
            if _is_business_day(cursor):
                counted += 1
            else:
                excluded += 1
        due = cursor
        detail = f"{j.count} business days from {clock_started_on.isoformat()}"

    return DeadlineComputation(
        student_ref=student_ref,
        jurisdiction=jurisdiction_key,
        rule_label=j.label,
        clock_started_on=clock_started_on,
        due_on=due,
        days_remaining=(due - today).days,
        excluded_days=excluded,
        explanation=(
            f"{detail}. {excluded} day(s) not counted under this rule. "
            f"Due {due.isoformat()}."
        ),
    )


def applicable_rungs(comp: DeadlineComputation) -> list[int]:
    """Every ladder rung the case has already fallen past, loosest first."""
    return sorted((r for r in ESCALATION_LADDER if comp.days_remaining <= r),
                  reverse=True)


def due_escalation(comp: DeadlineComputation, already_sent: list[int]) -> int | None:
    """The single rung to fire now, or None.

    Returns the TIGHTEST applicable rung, not the loosest. At six days out the
    fourteen-day warning is moot -- nobody wants a "14 days remaining" notice
    when six remain. A case that goes unnoticed until late therefore gets one
    accurate notice rather than a burst walking the entire ladder over three
    consecutive ticks.
    """
    applicable = applicable_rungs(comp)
    if not applicable:
        return None
    tightest = min(applicable)
    return None if tightest in already_sent else tightest


def superseded_by(rung: int) -> list[int]:
    """Rungs that firing `rung` retires -- itself and everything looser."""
    return [r for r in ESCALATION_LADDER if r >= rung]


def recompute(case: Case, *, today: date | None = None) -> DeadlineComputation:
    """Deadline for a case as it stands right now.

    Lives here rather than in agents/clock.py on purpose: the tick job must be
    able to do this arithmetic without importing an LLM framework, and this is
    the code path where a wrong answer has legal consequences.
    """
    if case.consent is None:
        raise ValueError(f"{case.student_ref} has no consent event; clock not started")
    return compute_deadline(
        student_ref=case.student_ref,
        jurisdiction_key=case.jurisdiction,
        clock_started_on=case.consent.consent_signed_on,
        calendar=demo_calendar(),
        today=today,
    )


def pending_escalation(case: Case, comp: DeadlineComputation) -> int | None:
    return due_escalation(comp, case.escalations_sent)
