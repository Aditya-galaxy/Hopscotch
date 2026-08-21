"""clock-agent -- owns the statutory deadline.

Identity: SPED admin. Reads dates and jurisdiction only; no narrative content,
no clinical fields.

Deliberately thin: the date arithmetic lives in deadlines.py as pure functions.
An LLM decides *when to escalate and to whom*; it never computes the deadline.
That boundary is the point -- a hallucinated date here is a lawsuit.
"""
from __future__ import annotations

from datetime import date

from google.adk.agents import LlmAgent

from ..config import FLASH
from ..deadlines import compute_deadline, due_escalation
from ..jurisdictions import demo_calendar
from ..schemas import Case, DeadlineComputation

INSTRUCTION = """\
You draft escalation notices for special education evaluation deadlines.

The due date is computed for you and is authoritative -- restate it exactly,
never recompute it, never round it, never describe it as "about" anything.

Write for a coordinator holding 300 other cases: lead with the student ref and
days remaining, then the single next action. No preamble.
"""

clock_agent = LlmAgent(
    name="clock_agent",
    model=FLASH,
    instruction=INSTRUCTION,
)


def recompute(case: Case, *, today: date | None = None) -> DeadlineComputation:
    if case.consent is None:
        raise ValueError(f"{case.student_ref} has no consent event; clock not started")
    return compute_deadline(
        student_ref=case.student_ref,
        jurisdiction_key=case.jurisdiction,
        clock_started_on=case.consent.consent_signed_on,
        calendar=demo_calendar(),
        today=today,
    )


def pending_escalation(case: Case, comp: DeadlineComputation) -> int | None:
    return due_escalation(comp, case.escalations_sent)
