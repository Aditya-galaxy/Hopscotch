"""intake-agent -- turns messy documents into a ConsentEvent.

Identity: front office. Sees raw inbound documents; never sees clinical fields.
Everything it reads came from outside the district, so everything it reads is
screened by Model Armor first.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from ..config import FLASH
from ..guardrails import screen_inbound
from ..schemas import ConsentEvent

INSTRUCTION = """\
You read special education referral paperwork that arrives as phone photos,
skewed scans, and forwarded email threads.

Extract exactly the ConsentEvent fields. Rules:
- Never invent a date. If the signature date is illegible or missing, return
  `consent_signed_on: null` and lower `confidence`. A statutory clock started
  from a guessed date is worse than one a human is asked to confirm, and the
  system routes nulls to a human by design.
- `student_ref` is the opaque id printed on the form. If the form shows only a
  name, return the name in `source_document` and leave `student_ref` empty --
  do not construct an identifier.
- `jurisdiction` comes from the school code's district mapping, not from your
  own knowledge of state law.

Return only the structured fields. No commentary.
"""

intake_agent = LlmAgent(
    name="intake_agent",
    model=FLASH,
    instruction=INSTRUCTION,
    output_schema=ConsentEvent,
)


def screened_extract(document_text: str, *, source: str) -> ConsentEvent:
    """The only way in. Screen, then extract.

    Callers do not get to skip the guardrail: a caller that screens separately
    can forget to, and this document arrived from outside the district. Model
    Armor rejects prompt injection hidden in a scanned form before any model
    reads it.
    """
    result = screen_inbound(document_text, source=source)
    if not result.allowed:
        raise PermissionError(
            f"Model Armor blocked {source}: {', '.join(result.findings)}")

    from ..adk_runner import run_structured
    return run_structured(intake_agent, result.sanitized, ConsentEvent)
