"""Inline guardrails: Model Armor on the boundary, Gemma on the handoff.

Two distinct jobs that are easy to conflate:

  screen_inbound()  -- Model Armor. Is this document trying to hijack the agent?
  redact_clinical() -- Gemma. Strip protected findings before a lower-privilege
                       agent, or the outside world, can see them.

Neither is optional. The first protects the fleet; the second protects the student.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import GEMMA, settings
from .telemetry import span


@dataclass(frozen=True)
class ScreenResult:
    allowed: bool
    findings: list[str]
    sanitized: str


def screen_inbound(text: str, *, source: str) -> ScreenResult:
    """Model Armor check on anything that entered from outside the district.

    TODO(day-7): call the Model Armor sanitizeUserPrompt endpoint against
    settings.armor_template. The local heuristic below exists so the pipeline
    is testable offline -- it is NOT the guardrail and must not ship as one.
    """
    with span("guardrail.screen_inbound", source=source, chars=len(text)) as s:
        if settings.armor_template:
            raise NotImplementedError(
                "Wire Model Armor here on day 7; see deploy/probe.sh output."
            )
        lowered = text.lower()
        tells = [
            p for p in (
                "ignore previous", "ignore prior", "disregard the above",
                "system prompt", "you are now", "mark this case closed",
            ) if p in lowered
        ]
        s.set_attribute("findings", len(tells))
        return ScreenResult(
            allowed=not tells,
            findings=tells,
            sanitized="" if tells else text,
        )


def redact_clinical(text: str, *, student_ref: str) -> tuple[str, bool]:
    """Gemma strips clinical findings before the family-facing handoff.

    TODO(day-8): call Gemma (config.GEMMA) with the redaction prompt. Returning
    (text, False) here means "not yet redacted" -- family_agent asserts on the
    boolean, so an unwired redactor fails closed rather than leaking.
    """
    with span("guardrail.redact_clinical", model=GEMMA, student_ref=student_ref):
        return text, False
