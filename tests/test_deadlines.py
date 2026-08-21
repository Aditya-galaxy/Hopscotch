"""The deadline math is the one thing here that must not be approximately right."""
from datetime import date

from agentx.deadlines import compute_deadline, due_escalation, superseded_by
from agentx.jurisdictions import demo_calendar

CAL = demo_calendar()


def _c(jur, start, today=date(2026, 9, 1)):
    return compute_deadline(
        student_ref="stu_test", jurisdiction_key=jur,
        clock_started_on=start, calendar=CAL, today=today,
    )


def test_federal_is_a_plain_calendar_count():
    comp = _c("US_FEDERAL", date(2026, 9, 1))
    assert comp.due_on == date(2026, 10, 31)
    assert comp.excluded_days == 0


def test_short_holiday_does_not_move_a_pausing_calendar_rule():
    # ST_ALPHA pauses only for breaks longer than 5 school days. The two-day
    # November closure must not shift the due date. Window is Oct 1 - Nov 30,
    # chosen so it contains that closure and NOT winter break.
    comp = _c("ST_ALPHA", date(2026, 10, 1))
    assert comp.due_on == date(2026, 11, 30)
    assert comp.excluded_days == 0


def test_winter_break_does_move_a_pausing_calendar_rule():
    # Same rule, but the window now spans an 8-weekday winter closure.
    comp = _c("ST_ALPHA", date(2026, 11, 15))
    naive = date(2027, 1, 14)
    assert comp.due_on > naive
    assert comp.excluded_days > 5


def test_school_day_rule_skips_weekends_and_closures():
    comp = _c("ST_BRAVO", date(2026, 11, 1))
    assert CAL.is_school_day(comp.due_on)
    assert comp.excluded_days > 15


def test_business_day_rule_skips_fixed_holidays():
    comp = _c("ST_CHARLIE", date(2026, 12, 1))
    assert comp.due_on.weekday() < 5
    assert (12, 25) != (comp.due_on.month, comp.due_on.day)


def test_ladder_picks_the_tightest_applicable_rung():
    # Six days out, both the 14- and 7-day rungs have been passed. Sending a
    # "14 days remaining" notice now would be wrong, so 7 wins.
    comp = _c("US_FEDERAL", date(2026, 9, 1), today=date(2026, 10, 25))
    assert comp.days_remaining == 6
    assert due_escalation(comp, already_sent=[]) == 7
    assert due_escalation(comp, already_sent=[7]) is None


def test_ladder_picks_the_loose_rung_when_only_it_applies():
    comp = _c("US_FEDERAL", date(2026, 9, 1), today=date(2026, 10, 21))
    assert comp.days_remaining == 10
    assert due_escalation(comp, already_sent=[]) == 14


def test_firing_a_tight_rung_retires_the_looser_ones():
    assert superseded_by(7) == [14, 7]
    assert superseded_by(2) == [14, 7, 2]
    assert superseded_by(14) == [14]
