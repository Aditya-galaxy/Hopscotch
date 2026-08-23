"""coordinator -- the supervisor.

Identity: SPED admin, elevated. Routes work, validates every return, and owns
the failure paths. The only agent on Pro, and only for adjudication: deciding
what to do when a worker's output is valid but implausible.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from ..config import SUPERVISOR
from ..schemas import DailyBrief

INSTRUCTION = """\
You supervise a fleet of special education compliance agents. You have two
jobs: adjudicating questionable worker output, and writing the coordinator's
daily brief. Both are the same skill -- knowing what actually matters out of a
hundred things that happened.

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
    model=SUPERVISOR,
    instruction=INSTRUCTION,
    # Without an output_schema ADK returns prose, and the first live run came
    # back as Markdown headings that failed to parse. The supervisor's only
    # invoked path today is the daily brief -- adjudication is handled
    # deterministically in supervisor/resilience.py -- so this is the shape.
    output_schema=DailyBrief,
)
