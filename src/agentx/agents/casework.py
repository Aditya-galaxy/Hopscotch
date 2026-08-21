"""casework-agent -- drafts statutory notices.

Identity: school psychology. Holds the most sensitive data in the system and
therefore gets the NARROWEST tool allowlist: it can read the case and write a
draft, and it can do nothing else. No outbound network, no email, no storage
outside the case document.

That inversion -- highest privilege, fewest tools -- is the security posture
worth narrating in the demo.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from ..config import FLASH
from ..schemas import DraftedNotice

INSTRUCTION = """\
You draft Prior Written Notice, evaluation plans, and meeting agendas for a
special education office.

- Statutory language is not yours to improve. Where a citation is required,
  cite it; where you are unsure a citation applies, omit it and say so in the
  body rather than guessing at a section number.
- Write at a reading level a parent can follow without a lawyer.
- Set contains_clinical=true whenever the draft references evaluation findings.
  Downstream redaction depends on that flag being honest.
"""

casework_agent = LlmAgent(
    name="casework_agent",
    model=FLASH,
    instruction=INSTRUCTION,
    output_schema=DraftedNotice,
)
