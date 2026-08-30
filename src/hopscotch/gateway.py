"""Agent Gateway: the enforcement point.

Two levels, and the second is the one that matters.

  authorize()  refuses a call an agent has no scope for. Necessary, and the
               level most systems stop at.

  project()    shapes the DATA to the caller's identity. family-agent does not
               receive clinical fields and then decline to use them -- it never
               receives them. A check can be forgotten at a new call site; a
               projection cannot leak a field it never returned.

Every denial is audited. A silent refusal is unfixable: the coordinator sees an
agent "not working" with no way to learn it was a policy decision.
"""
from __future__ import annotations

from dataclasses import dataclass

from .registry import AgentCard, ScopeDenied, authorize, load_cards
from .schemas import Case, Sensitivity
from .telemetry import span

# What each read scope is allowed to see. Ordered least to most sensitive.
SCOPE_SENSITIVITY: dict[str, Sensitivity] = {
    "case.read_redacted": Sensitivity.DIRECTORY,
    # A parent's portal shows status, dates and the letters actually sent --
    # not the clinical file. That is a PRODUCT decision, not a statement about
    # their rights: FERPA gives parents the right to inspect the complete
    # record, which is a records request handled by a person, and the portal
    # says so on the page rather than quietly implying the file is all there is.
    "case.read_own": Sensitivity.ADMINISTRATIVE,
    "case.read_dates": Sensitivity.ADMINISTRATIVE,
    "case.read": Sensitivity.ADMINISTRATIVE,
    "case.read_full": Sensitivity.CLINICAL,
}

_RANK = {Sensitivity.DIRECTORY: 0, Sensitivity.ADMINISTRATIVE: 1,
         Sensitivity.CLINICAL: 2}

# Field-level classification. Anything not listed is treated as CLINICAL --
# fail closed, so a field added later is withheld until someone classifies it
# rather than leaking by default.
FIELD_SENSITIVITY: dict[str, Sensitivity] = {
    "student_ref": Sensitivity.DIRECTORY,
    "school_code": Sensitivity.DIRECTORY,
    "jurisdiction": Sensitivity.DIRECTORY,
    "stage": Sensitivity.DIRECTORY,
    "deadline": Sensitivity.ADMINISTRATIVE,
    "escalations_sent": Sensitivity.ADMINISTRATIVE,
    "updated_at": Sensitivity.ADMINISTRATIVE,
    "consent": Sensitivity.ADMINISTRATIVE,
    # Nested consent fields, classified individually. The clinical narrative
    # lives here beside ordinary administrative dates, which is exactly why a
    # coarse allow-list on the parent block would leak it.
    "consent_signed_on": Sensitivity.ADMINISTRATIVE,
    "received_on": Sensitivity.ADMINISTRATIVE,
    "confidence": Sensitivity.ADMINISTRATIVE,
    # The RAW intake document, verbatim. It is the least redacted thing in the
    # record: the student's actual name, the referral reason in the parent's
    # own words, sometimes an address. It was classified ADMINISTRATIVE, which
    # explicitly downgraded the most sensitive field in the case below the
    # fail-closed default -- and the case page rendered it, name and all, to an
    # identity whose header says "clinical detail withheld". Everything derived
    # FROM this document is classified individually below; the document itself
    # is a superset of all of them, so it takes the highest tier of any part.
    "source_document": Sensitivity.CLINICAL,
    "referral_reason": Sensitivity.CLINICAL,
}


@dataclass(frozen=True)
class Denial:
    agent: str
    scope: str
    reason: str


def ceiling_for(scopes) -> Sensitivity:
    """The most sensitive tier these scopes permit.

    Takes scopes rather than a card, so the SAME classification governs an
    agent and a person. A liaison signing in to the dashboard and family-agent
    calling a tool get identical answers, because they are asking the same
    question of the same table.
    """
    tiers = [SCOPE_SENSITIVITY[s] for s in scopes if s in SCOPE_SENSITIVITY]
    if not tiers:
        return Sensitivity.DIRECTORY
    return max(tiers, key=lambda t: _RANK[t])


def max_sensitivity(card: AgentCard) -> Sensitivity:
    """The most sensitive tier this agent's scopes permit."""
    return ceiling_for(card.scopes)


def project_for_scopes(scopes, case: Case) -> dict:
    """Return only the fields these scopes may see.

    The clinical narrative lives inside `consent.referral_reason`, so the
    consent block is walked rather than passed through whole -- a nested field
    is exactly where a coarse allow-list leaks.
    """
    ceiling = _RANK[ceiling_for(scopes)]
    raw = case.model_dump(mode="json")
    out: dict = {}
    for key, value in raw.items():
        tier = FIELD_SENSITIVITY.get(key, Sensitivity.CLINICAL)
        if _RANK[tier] > ceiling:
            continue
        if key == "consent" and isinstance(value, dict):
            value = {k: v for k, v in value.items()
                     if _RANK[FIELD_SENSITIVITY.get(k, Sensitivity.CLINICAL)] <= ceiling}
        out[key] = value
    return out


def project(card: AgentCard, case: Case) -> dict:
    """Agent-facing projection. Delegates, so agents and people cannot drift."""
    return project_for_scopes(card.scopes, case)


class Gateway:
    """Wraps privileged work. Nothing reaches a tool without passing here."""

    def __init__(self, cards: list[AgentCard] | None = None, *, auditor=None) -> None:
        self._cards = cards if cards is not None else load_cards()
        self._by_name = {c.name: c for c in self._cards}
        self._auditor = auditor
        self.denials: list[Denial] = []

    def card(self, agent: str) -> AgentCard:
        card = self._by_name.get(agent)
        if card is None:
            raise ScopeDenied(f"{agent} is not published to the registry")
        return card

    def check(self, agent: str, scope: str) -> None:
        with span("gateway.check", agent=agent, scope=scope) as s:
            try:
                authorize(self._cards, agent, scope)
            except ScopeDenied as e:
                s.set_attribute("decision", "deny")
                self._record(Denial(agent, scope, str(e)))
                raise
            s.set_attribute("decision", "allow")

    def read_case(self, agent: str, case: Case, *, scope: str = "case.read") -> dict:
        """Authorize, then hand back only what this identity may see."""
        self.check(agent, scope)
        return project(self.card(agent), case)

    def _record(self, denial: Denial) -> None:
        self.denials.append(denial)
        if self._auditor is not None:
            self._auditor(denial)
            return
        try:
            from . import store
            from .idempotency import effect_id
            store.audit(
                "scope_denied",
                effect_id=effect_id("denial", denial.agent, denial.scope),
                student_ref=None, agent=denial.agent, scope=denial.scope,
                reason=denial.reason,
            )
        except Exception:  # auditing must never mask the denial itself
            pass
