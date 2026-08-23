"""Human corrections.

The property: a coordinator accountable for the outcome can override the fleet,
and doing so is recorded rather than silent. A system that can be wrong and
cannot be corrected gets worked around in a spreadsheet, which is the state it
was built to replace.
"""
from datetime import date, datetime, timezone

import pytest

from hopscotch.deadlines import ClockCannotStart, latest_correction, recompute
from hopscotch.schemas import Case, CaseStage, ConsentEvent, Correction


def a_case(signed=date(2026, 9, 1)) -> Case:
    return Case(
        student_ref="stu_0001", school_code="EL-004", jurisdiction="US_FEDERAL",
        stage=CaseStage.CONSENT_RECEIVED,
        consent=ConsentEvent(
            student_ref="stu_0001", school_code="EL-004",
            jurisdiction="US_FEDERAL", consent_signed_on=signed,
            received_on=signed, confidence=0.9, source_document="c.pdf"))


def correction(field, value, by="coordinator@district.org", **kw):
    return Correction(field=field, value=value, reason=kw.pop("reason", "district rule differs"),
                      by=by, **kw)


def test_an_overridden_due_date_wins():
    """The jurisdiction table is illustrative and districts know their own
    rules. The human is the authority, not the table."""
    case = a_case()
    computed = recompute(case, today=date(2026, 9, 1))
    case.corrections.append(correction("due_on", date(2026, 11, 15),
                                       computed_was=computed.due_on.isoformat()))

    out = recompute(case, today=date(2026, 9, 1))
    assert out.due_on == date(2026, 11, 15)
    assert out.due_on != computed.due_on


def test_the_computed_value_survives_beside_the_override():
    """A coordinator who cannot see what the system thought has no way to judge
    whether it is improving."""
    case = a_case()
    computed = recompute(case, today=date(2026, 9, 1))
    case.corrections.append(correction(
        "due_on", date(2026, 11, 15), reason="state counts school days",
        computed_was=computed.due_on.isoformat()))

    out = recompute(case, today=date(2026, 9, 1))
    assert computed.due_on.isoformat() in out.explanation
    assert "state counts school days" in out.explanation
    assert "coordinator@district.org" in out.explanation


def test_supplying_a_missing_consent_date_unblocks_the_case():
    """The illegible-signature path. intake returns null, the clock refuses to
    start, and a human reading the actual form is how it gets unstuck."""
    case = a_case()
    case.consent.consent_signed_on = None
    with pytest.raises(ClockCannotStart):
        recompute(case, today=date(2026, 10, 1))

    case.corrections.append(correction(
        "consent_signed_on", date(2026, 9, 3), reason="read the paper form"))
    out = recompute(case, today=date(2026, 10, 1))
    assert out.due_on == date(2026, 11, 2)
    assert "read the paper form" in out.explanation


def test_the_most_recent_correction_wins():
    case = a_case()
    case.corrections.append(correction(
        "due_on", date(2026, 11, 1),
        at=datetime(2026, 10, 1, tzinfo=timezone.utc)))
    case.corrections.append(correction(
        "due_on", date(2026, 12, 1),
        at=datetime(2026, 10, 5, tzinfo=timezone.utc)))
    assert recompute(case, today=date(2026, 10, 6)).due_on == date(2026, 12, 1)


def test_a_correction_requires_a_reason():
    """An unexplained override is indistinguishable from a mistake."""
    with pytest.raises(Exception):
        Correction(field="due_on", value=date(2026, 11, 1), by="x@d.org")


def test_correcting_reopens_escalations():
    """A case corrected from overdue to three-weeks-out must not stay silent
    because its rungs were already spent."""
    from hopscotch.deadlines import pending_escalation

    case = a_case()
    case.escalations_sent = [14, 7, 2]
    case.corrections.append(correction("due_on", date(2026, 12, 20)))
    case.escalations_sent = []          # what store.apply_correction does

    comp = recompute(case, today=date(2026, 12, 13))
    assert pending_escalation(case, comp) == 7


def test_latest_correction_ignores_other_fields():
    case = a_case()
    case.corrections.append(correction("consent_signed_on", date(2026, 9, 3)))
    assert latest_correction(case, "due_on") is None
    assert latest_correction(case, "consent_signed_on") is not None


def test_only_case_write_may_correct():
    from hopscotch.auth import NotPermitted, Principal, Role

    Principal(email="c@d.org", role=Role.COORDINATOR).require("case.write")
    for role in (Role.LIAISON, Role.PSYCHOLOGIST, Role.BUSINESS):
        with pytest.raises(NotPermitted):
            Principal(email="x@d.org", role=role).require("case.write")
