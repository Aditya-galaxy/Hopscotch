"""Agent Registry and the gateway authorization check.

These run against the real registry/*.agent.yaml cards, so a card that stops
parsing breaks the build rather than silently publishing an agent with no
scopes -- which is exactly what happened once and is why the first test exists.
"""
import pytest

from hopscotch.registry import AgentCard, ScopeDenied, authorize, load_cards

CARDS = load_cards()
BY_NAME = {c.name: c for c in CARDS}


def test_all_five_agents_are_published():
    assert set(BY_NAME) == {
        "coordinator", "intake-agent", "clock-agent",
        "casework-agent", "family-agent",
    }


def test_scopes_parse_as_a_list_not_one_string():
    """Regression. The cards were generated with a shell loop that collapsed
    'a,b,c' into a single list item, so every agent published with exactly one
    scope named 'case.read case.write worker.invoke'. It parsed, it published,
    and it authorized nothing correctly."""
    for card in CARDS:
        assert card.scopes, f"{card.name} has no scopes"
        for scope in card.scopes:
            assert " " not in scope, (
                f"{card.name} scope {scope!r} contains a space -- "
                "the YAML list collapsed")


def test_every_agent_has_its_own_identity():
    ids = [c.spiffe_id for c in CARDS]
    assert len(set(ids)) == len(ids), "a SPIFFE id is shared between agents"
    assert all(i.startswith("spiffe://") for i in ids)


# --- the gateway ------------------------------------------------------------

def test_declared_scope_is_allowed():
    authorize(CARDS, "clock-agent", "case.read_dates")


def test_undeclared_scope_is_denied_with_a_reason():
    with pytest.raises(ScopeDenied) as e:
        authorize(CARDS, "clock-agent", "case.read_full")
    assert "may not" in str(e.value)
    assert "case.read_dates" in str(e.value), "denial does not say what IS allowed"


def test_family_agent_cannot_reach_clinical_data():
    """The privilege boundary, as a test rather than a diagram.

    family-agent is the only agent that talks to the outside world, so it is
    the one that must never hold clinical scope.
    """
    with pytest.raises(ScopeDenied):
        authorize(CARDS, "family-agent", "case.read_full")
    authorize(CARDS, "casework-agent", "case.read_full")


def test_unregistered_agent_holds_no_scopes():
    """Deny by default. An agent nobody published cannot inherit anything."""
    with pytest.raises(ScopeDenied) as e:
        authorize(CARDS, "rogue-agent", "case.read")
    assert "not published" in str(e.value)


def test_privilege_inversion_holds():
    """Most sensitive data, fewest tools.

    casework-agent reads full clinical case detail and can do almost nothing
    else. family-agent reaches families and holds more tools but no clinical
    scope. If someone later widens casework-agent, this fails.
    """
    casework = BY_NAME["casework-agent"]
    family = BY_NAME["family-agent"]
    assert "case.read_full" in casework.scopes
    assert len(casework.scopes) < len(family.scopes)
    assert not any("read_full" in s for s in family.scopes)
