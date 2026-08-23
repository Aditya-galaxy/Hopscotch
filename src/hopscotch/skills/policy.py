"""Trust policy for skill installation.

This module is the project's actual argument, so it is worth stating plainly.

Hermes Agent ships a real static scanner with a trust-tiered install policy.
Read from its source (tools/skills_guard.py), that policy is:

    community      safe=allow  caution=BLOCK  dangerous=block
    agent-created  safe=allow  caution=allow  dangerous=ask

...and their own comment notes the agent-created gate "only runs when
skills.guard_agent_created is enabled -- off by default."

So identical content is blocked when downloaded and installed when the agent
wrote it for itself. That is backwards. A community skill was at least authored
by a human who could be identified. A self-authored skill was written by a
model that may have read a hostile web page ten minutes earlier, and nobody
reviewed it at all.

Hopscotch inverts it: AGENT_AUTHORED is the STRICTEST tier, not the loosest. And
the table is org-configurable data rather than a hardcoded Python literal, so a
district can tighten it without shipping a new build, and a compromised
publisher can be demoted at runtime.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .model import Decision, Origin, Verdict

# origin -> verdict -> decision
DEFAULT_POLICY: dict[Origin, dict[Verdict, Decision]] = {
    Origin.BUILTIN: {
        Verdict.SAFE: Decision.APPROVE,
        Verdict.CAUTION: Decision.APPROVE,
        Verdict.DANGEROUS: Decision.QUARANTINE,
    },
    Origin.TRUSTED_REPO: {
        Verdict.SAFE: Decision.APPROVE,
        Verdict.CAUTION: Decision.APPROVE,
        Verdict.DANGEROUS: Decision.REJECT,
    },
    Origin.COMMUNITY: {
        Verdict.SAFE: Decision.APPROVE,
        Verdict.CAUTION: Decision.QUARANTINE,
        Verdict.DANGEROUS: Decision.REJECT,
    },
    Origin.CROSS_RUNTIME: {
        # Imported from another runtime, so it passed *someone else's* policy,
        # under a threat model we cannot see. Treat as unreviewed.
        Verdict.SAFE: Decision.QUARANTINE,
        Verdict.CAUTION: Decision.REJECT,
        Verdict.DANGEROUS: Decision.REJECT,
    },
    Origin.AGENT_AUTHORED: {
        # The inversion. Nothing an agent wrote for itself becomes durable
        # without a human looking at it, even when it scans clean -- because
        # "scans clean" is exactly what a well-written injection looks like.
        Verdict.SAFE: Decision.QUARANTINE,
        Verdict.CAUTION: Decision.REJECT,
        Verdict.DANGEROUS: Decision.REJECT,
    },
}


class TrustPolicy(BaseModel):
    """Org-configurable. Load from Firestore so it can change without a deploy."""

    table: dict[Origin, dict[Verdict, Decision]] = Field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_POLICY.items()}
    )
    trusted_publishers: set[str] = Field(default_factory=set)

    def decide(self, origin: Origin, verdict: Verdict) -> Decision:
        return self.table[origin][verdict]

    def demote(self, publisher: str) -> None:
        """A trusted publisher gets compromised at 3am. This is the response."""
        self.trusted_publishers.discard(publisher)

    def classify(self, publisher: str | None) -> Origin:
        if publisher and publisher in self.trusted_publishers:
            return Origin.TRUSTED_REPO
        return Origin.COMMUNITY
