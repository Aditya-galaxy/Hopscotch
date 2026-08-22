"""The capability gate.

Nothing becomes a durable capability without passing through here. Downloaded,
imported from another runtime, or written by the agent for itself -- one door.

Two properties matter more than the reviewers themselves:

  Fail closed. A reviewer that errors, times out, or is not yet wired does NOT
  become an approval. An unavailable reviewer downgrades the decision, because
  "we could not check" and "we checked and it was fine" are different answers
  and only one of them is safe to conflate with yes.

  Explain. Every decision carries the reasoning that produced it, into the audit
  log. A quarantine a coordinator cannot understand is a quarantine they will
  eventually disable.
"""
from __future__ import annotations

from .model import (
    Decision, Origin, ReviewerResult, ScanReport, SkillPackage, Verdict,
)
from .policy import TrustPolicy
from .reviewers import (
    InjectionReviewer, IntentReviewer, Reviewer, StructuralReviewer, TriageReviewer,
)
from ..telemetry import span

_ORDER = {Verdict.SAFE: 0, Verdict.CAUTION: 1, Verdict.DANGEROUS: 2}
_STRICTNESS = {Decision.APPROVE: 0, Decision.QUARANTINE: 1, Decision.REJECT: 2}


def default_reviewers() -> list[Reviewer]:
    """Cheapest first, so obvious junk never reaches a paid model call."""
    return [StructuralReviewer(), TriageReviewer(), IntentReviewer(), InjectionReviewer()]


def worst(verdicts: list[Verdict]) -> Verdict:
    return max(verdicts, key=lambda v: _ORDER[v], default=Verdict.SAFE)


def review(
    pkg: SkillPackage,
    *,
    reviewers: list[Reviewer] | None = None,
    policy: TrustPolicy | None = None,
    require_all: bool = True,
) -> ScanReport:
    reviewers = default_reviewers() if reviewers is None else reviewers
    policy = policy or TrustPolicy()
    results: list[ReviewerResult] = []
    unavailable: list[str] = []

    with span("skills.gate", skill=pkg.name, origin=pkg.origin.value) as s:
        for r in reviewers:
            try:
                results.append(r.review(pkg))
            except NotImplementedError as e:
                unavailable.append(r.name)
                results.append(ReviewerResult(reviewer=r.name, ok=False,
                                              note=f"not wired: {e}"))
            except Exception as e:
                unavailable.append(r.name)
                results.append(ReviewerResult(reviewer=r.name, ok=False,
                                              note=f"{type(e).__name__}: {e}"))

        verdict = worst([r.verdict for r in results if r.ok])
        decision = policy.decide(pkg.origin, verdict)
        why = [f"origin={pkg.origin.value}", f"verdict={verdict.value}"]

        if unavailable and require_all and decision is Decision.APPROVE:
            decision = Decision.QUARANTINE
            why.append(
                "downgraded to quarantine: "
                f"{', '.join(unavailable)} could not run, and an unchecked "
                "skill is not a checked one"
            )

        counts = {}
        for f in (f for r in results for f in r.findings):
            counts[f.category.value] = counts.get(f.category.value, 0) + 1
        if counts:
            why.append("findings: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

        s.set_attribute("verdict", verdict.value)
        s.set_attribute("decision", decision.value)

        return ScanReport(
            skill_name=pkg.name, content_hash=pkg.content_hash, origin=pkg.origin,
            verdict=verdict, decision=decision, reasoning="; ".join(why),
            results=results,
        )


def stricter_of(a: Decision, b: Decision) -> Decision:
    return a if _STRICTNESS[a] >= _STRICTNESS[b] else b
