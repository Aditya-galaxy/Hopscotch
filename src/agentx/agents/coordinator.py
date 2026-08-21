"""coordinator -- the supervisor.

Identity: SPED admin, elevated. Routes work, validates every return, and owns
the failure paths. The only agent on Pro, and only for adjudication: deciding
what to do when a worker's output is valid but implausible.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from ..config import PRO

INSTRUCTION = """\
You supervise a fleet of special education compliance agents.

You are called when a worker returned something structurally valid but
questionable -- a deadline that moved unexpectedly, an extraction with low
confidence, a notice citing an unfamiliar statute.

Decide exactly one: ACCEPT, RETRY_WITH_NOTE, or ESCALATE_TO_HUMAN.

Bias hard toward ESCALATE_TO_HUMAN. A coordinator reviewing an unnecessary
flag loses a minute. A missed evaluation deadline costs the district a due
process complaint and the student a year. Those are not symmetric.
"""

coordinator = LlmAgent(
    name="coordinator",
    model=PRO,
    instruction=INSTRUCTION,
)
