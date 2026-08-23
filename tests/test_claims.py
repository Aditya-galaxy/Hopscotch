"""Claim readiness. Every test is a real, published denial reason.

The design bias is conservative on purpose: over-claiming triggers recoupment,
which is worse than the underclaiming this is meant to fix. So the module
reports what would be denied and never generates a claim, and an over-bill
blocks while an under-bill only flags.
"""
from datetime import date

import pytest

from hopscotch.claims import MINUTES_PER_UNIT, assess, parse_narrative
from hopscotch.schemas import IEPService, ServiceDelivery

IEP = IEPService(
    goal_ref="G-3", service="speech-language therapy, individual",
    minutes_per_session=30, sessions_per_week=2,
    provider_type="speech-language pathologist",
    starts_on=date(2026, 9, 1), ends_on=date(2027, 6, 30))


def a_delivery(**over) -> ServiceDelivery:
    base = dict(
        student_ref="stu_0001", goal_ref="G-3", service_date=date(2026, 10, 6),
        minutes=30, units_billed=2,
        note="Individual speech session. Worked on /r/ production in structured "
             "phrases, 70% accuracy with minimal cueing.",
        provider_npi="1234567890", provider_type="speech-language pathologist",
        provider_license_expires=date(2027, 12, 31))
    base.update(over)
    return ServiceDelivery(**base)


class Stub:
    """Stands in for the narrative reviewer."""
    def __init__(self, text="CONSISTENT\nMatches the authorized service."):
        self._text = text
        self.models = self

    def generate_content(self, **kw):
        return type("R", (), {"text": self._text})()


def check(readiness, name):
    return next(c for c in readiness.checks if c.requirement == name)


# --- the happy path ----------------------------------------------------------

def test_a_clean_session_is_billable():
    r = assess(a_delivery(), IEP, medicaid_eligible=True, client=Stub())
    assert r.billable
    assert r.blocking_failures == []
    assert r.reviewed_semantically


# --- published denial reasons ------------------------------------------------

def test_ineligible_student_blocks():
    r = assess(a_delivery(), IEP, medicaid_eligible=False, client=Stub())
    assert not r.billable
    assert "Medicaid eligible" in r.blocking_failures[0].requirement


def test_expired_licence_on_the_service_date_blocks():
    """Credentialing lapses are among the most frequently cited findings."""
    r = assess(a_delivery(provider_license_expires=date(2026, 9, 30)), IEP,
               medicaid_eligible=True, client=Stub())
    assert not r.billable
    assert "expired" in check(r, "provider licence valid on the service date").detail


def test_missing_npi_blocks():
    r = assess(a_delivery(provider_npi=""), IEP, medicaid_eligible=True, client=Stub())
    assert not r.billable


def test_unapproved_provider_type_blocks():
    r = assess(a_delivery(provider_type="teaching assistant"), IEP,
               medicaid_eligible=True, client=Stub())
    assert not r.billable


def test_service_outside_the_iep_window_blocks():
    r = assess(a_delivery(service_date=date(2026, 8, 15)), IEP,
               medicaid_eligible=True, client=Stub())
    assert not r.billable


def test_over_billing_blocks_but_under_billing_only_flags():
    """Asymmetric on purpose. Over-billing is recoupment; under-billing is the
    district's own money left on the table, which is worth surfacing but is not
    a reason to refuse the claim."""
    over = assess(a_delivery(minutes=30, units_billed=4), IEP,
                  medicaid_eligible=True, client=Stub())
    assert not over.billable
    assert "OVER-BILLED" in check(over, "billed units match documented minutes").detail

    under = assess(a_delivery(minutes=30, units_billed=1), IEP,
                   medicaid_eligible=True, client=Stub())
    assert under.billable, "under-billing should not block the claim"
    assert under.audit_risks, "under-billing should still be surfaced"
    assert "unclaimed" in under.audit_risks[0].detail


def test_thin_note_blocks():
    r = assess(a_delivery(note="Session held."), IEP,
               medicaid_eligible=True, client=Stub())
    assert not r.billable


# --- the check rules cannot make ---------------------------------------------

def test_group_note_against_individual_authorization_blocks():
    """The three-way consistency test. Nothing in the rule checks catches this:
    eligible student, valid licence, right provider type, correct units, real
    note. The only thing wrong is that the note describes a GROUP session while
    the IEP authorizes individual therapy — and there is no pattern for that."""
    r = assess(
        a_delivery(note="Small group session with three peers. Practiced "
                        "turn-taking and topic maintenance in conversation."),
        IEP, medicaid_eligible=True,
        client=Stub("DISCREPANT\nNote describes a group session; IEP authorizes "
                    "individual therapy."))
    assert not r.billable
    failure = check(r, "note is consistent with the authorized service")
    assert failure.blocking
    assert "group" in failure.detail.lower()


def test_rule_checks_alone_pass_that_same_session():
    """Proves the point above: strip the narrative reviewer and it looks clean."""
    r = assess(
        a_delivery(note="Small group session with three peers. Practiced "
                        "turn-taking and topic maintenance in conversation."),
        IEP, medicaid_eligible=True, client=Stub())
    rule_failures = [c for c in r.blocking_failures
                     if "consistent with" not in c.requirement]
    assert rule_failures == [], "a rule check caught it; it should not have"


def test_unclear_note_blocks():
    """If an auditor cannot follow the story, the claim does not survive. A note
    too vague to match against the IEP is the 'incomplete documentation'
    denial, so UNCLEAR blocks alongside DISCREPANT."""
    r = assess(a_delivery(), IEP, medicaid_eligible=True,
               client=Stub("UNCLEAR\nToo vague to tell."))
    assert not r.billable
    assert r.blocking_failures


# --- fail closed -------------------------------------------------------------

def test_unreviewable_note_is_not_marked_billable():
    """Same rule as the skill gate: unchecked is not clean."""
    class Broken:
        models = property(lambda self: self)
        def generate_content(self, **kw):
            raise RuntimeError("no credentials")

    r = assess(a_delivery(), IEP, medicaid_eligible=True, client=Broken())
    assert not r.billable
    assert not r.reviewed_semantically
    assert r.blocking_failures == [], "a missing review is a gap, not a denial"


def test_units_are_fifteen_minutes():
    assert MINUTES_PER_UNIT == 15


def test_unparseable_verdict_raises():
    with pytest.raises(ValueError):
        parse_narrative("probably fine?")
