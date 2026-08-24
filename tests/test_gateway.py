"""The privilege boundary, enforced rather than described.

Two levels are tested separately because they fail differently. A missing
authorize() call is a bug at one call site. A projection that returns a field
it should not is a leak at every call site at once.
"""
from datetime import date

import pytest

from hopscotch.gateway import Gateway, max_sensitivity, project
from hopscotch.registry import ScopeDenied, load_cards
from hopscotch.schemas import Case, CaseStage, ConsentEvent, Sensitivity

CARDS = load_cards()
BY_NAME = {c.name: c for c in CARDS}

CLINICAL_TEXT = "Psychological evaluation indicates significant processing deficit"


def a_case() -> Case:
    return Case(
        student_ref="stu_0001", school_code="EL-004", jurisdiction="US_FEDERAL",
        stage=CaseStage.CONSENT_RECEIVED,
        consent=ConsentEvent(
            student_ref="stu_0001", school_code="EL-004",
            jurisdiction="US_FEDERAL", consent_signed_on=date(2026, 9, 1),
            received_on=date(2026, 9, 2), referral_reason=CLINICAL_TEXT,
            confidence=0.95, source_document="consent.pdf"),
    )


# --- level 1: authorization --------------------------------------------------

def test_gateway_allows_a_declared_scope():
    Gateway(CARDS, auditor=lambda d: None).check("clock-agent", "case.read_dates")


def test_gateway_denies_and_records():
    denials = []
    gw = Gateway(CARDS, auditor=denials.append)
    with pytest.raises(ScopeDenied):
        gw.check("family-agent", "case.read_full")
    assert len(denials) == 1
    assert denials[0].agent == "family-agent"
    assert denials[0].scope == "case.read_full"
    assert "may not" in denials[0].reason


def test_denial_is_audited_not_silent():
    """A silent refusal is unfixable -- the coordinator sees an agent 'not
    working' with no way to learn it was policy."""
    gw = Gateway(CARDS, auditor=lambda d: None)
    with pytest.raises(ScopeDenied):
        gw.check("rogue-agent", "case.read")
    assert gw.denials and "not published" in gw.denials[0].reason


# --- level 2: projection -----------------------------------------------------

def test_casework_agent_sees_the_clinical_narrative():
    view = project(BY_NAME["casework-agent"], a_case())
    assert view["consent"]["referral_reason"] == CLINICAL_TEXT


def test_family_agent_never_receives_clinical_fields():
    """Not 'declines to use them' -- never receives them.

    A check can be forgotten at a new call site. A projection cannot leak a
    field it never returned.
    """
    view = project(BY_NAME["family-agent"], a_case())
    assert "referral_reason" not in view.get("consent", {})
    assert CLINICAL_TEXT not in str(view)


def test_clock_agent_gets_dates_but_not_narrative():
    view = project(BY_NAME["clock-agent"], a_case())
    assert view["consent"]["consent_signed_on"] == "2026-09-01"
    assert "referral_reason" not in view["consent"]


def test_unclassified_fields_fail_closed():
    """A field added later is withheld until someone classifies it.

    The alternative -- unlisted means public -- means every future schema
    change is a potential leak that nobody reviews.
    """
    from hopscotch.gateway import FIELD_SENSITIVITY, _RANK
    case = a_case()
    for field in case.model_dump(mode="json"):
        tier = FIELD_SENSITIVITY.get(field, Sensitivity.CLINICAL)
        assert tier in _RANK, f"{field} classified as something unrankable"
    view = project(BY_NAME["family-agent"], case)
    assert set(view) <= set(FIELD_SENSITIVITY), "an unclassified field was projected"


def test_read_case_authorizes_before_projecting():
    gw = Gateway(CARDS, auditor=lambda d: None)
    with pytest.raises(ScopeDenied):
        gw.read_case("family-agent", a_case(), scope="case.read_full")
    view = gw.read_case("family-agent", a_case(), scope="case.read_redacted")
    assert CLINICAL_TEXT not in str(view)


def test_sensitivity_ceilings_match_the_privilege_inversion():
    assert max_sensitivity(BY_NAME["casework-agent"]) is Sensitivity.CLINICAL
    assert max_sensitivity(BY_NAME["family-agent"]) is Sensitivity.DIRECTORY
    assert max_sensitivity(BY_NAME["clock-agent"]) is Sensitivity.ADMINISTRATIVE


# --- one classification for agents and humans --------------------------------

def test_a_human_liaison_sees_exactly_what_family_agent_sees():
    """The projection is keyed on SCOPES, not on whether the caller is a
    process. A liaison signing in to the dashboard and family-agent calling a
    tool are asking the same question of the same table, so they must get the
    same answer -- otherwise the browser becomes the way around the boundary.
    """
    from hopscotch.auth import Principal, Role
    from hopscotch.gateway import project_for_scopes

    case = a_case()
    agent_view = project(BY_NAME["family-agent"], case)
    human_view = project_for_scopes(
        Principal(email="liaison@d.org", role=Role.LIAISON).scopes, case)

    assert CLINICAL_TEXT not in str(human_view)
    assert set(human_view) == set(agent_view)


def test_a_business_officer_gets_no_clinical_detail():
    from hopscotch.auth import Principal, Role
    from hopscotch.gateway import project_for_scopes

    view = project_for_scopes(
        Principal(email="cfo@d.org", role=Role.BUSINESS).scopes, a_case())
    assert CLINICAL_TEXT not in str(view)
    assert "referral_reason" not in view.get("consent", {})


def test_psychologist_sees_the_narrative_a_liaison_cannot():
    from hopscotch.auth import Principal, Role
    from hopscotch.gateway import project_for_scopes

    psych = project_for_scopes(
        Principal(email="p@d.org", role=Role.PSYCHOLOGIST).scopes, a_case())
    assert psych["consent"]["referral_reason"] == CLINICAL_TEXT
