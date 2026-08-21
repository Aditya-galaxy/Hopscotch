"""family-agent -- the only agent that talks to the outside world.

Identity: family liaison. Receives a REDACTED case view. It cannot read
clinical fields because it is never handed them -- Gemma strips them first and
this agent asserts on the redaction flag, so an unwired redactor fails closed.

Multimodal outputs: Chirp for the spoken notice, Veo for the timeline explainer.
Both are generated once per case and cached; neither is called from a demo loop.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from ..config import FLASH
from ..guardrails import redact_clinical
from ..schemas import DraftedNotice, FamilyPacket

INSTRUCTION = """\
You turn an internal special education notice into something a parent will
actually read, in their home language.

- Plain language. No acronyms without expansion on first use.
- Never restate a clinical finding, a diagnosis, or a test score. If the source
  text still contains one, stop and report it rather than paraphrasing it.
- Always state the date by which the district must act, and what the family can
  do if that date passes.
"""

family_agent = LlmAgent(
    name="family_agent",
    model=FLASH,
    instruction=INSTRUCTION,
    output_schema=FamilyPacket,
)


def prepare_handoff(notice: DraftedNotice) -> str:
    """Redaction gate. Clinical text does not cross this line un-stripped."""
    text, redacted = redact_clinical(notice.body, student_ref=notice.student_ref)
    if notice.contains_clinical and not redacted:
        raise PermissionError(
            f"refusing family handoff for {notice.student_ref}: "
            "clinical content present and redaction not applied"
        )
    return text
