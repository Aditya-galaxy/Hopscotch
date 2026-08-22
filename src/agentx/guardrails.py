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

    Same boundary as the skill gate's injection reviewer, different subject:
    there it is a capability the agent will absorb, here it is a scanned
    evaluation that arrived from a parent's phone. Both can carry instructions
    aimed at the model.
    """
    with span("guardrail.screen_inbound", source=source, chars=len(text)) as s:
        from .armor import screen

        result = screen(text, subject=source)
        s.set_attribute("matched", result.matched)
        if result.matched:
            findings = [f"{f.detail}"
                        + (f"@{f.confidence}" if f.confidence else "")
                        for f in result.findings]
            return ScreenResult(allowed=False, findings=findings, sanitized="")
        return ScreenResult(allowed=True, findings=[], sanitized=text)


def redact_clinical(text: str, *, student_ref: str) -> tuple[str, bool]:
    """Gemma strips clinical findings before the family-facing handoff.

    TODO(day-8): call Gemma (config.GEMMA) with the redaction prompt. Returning
    (text, False) here means "not yet redacted" -- family_agent asserts on the
    boolean, so an unwired redactor fails closed rather than leaking.
    """
    with span("guardrail.redact_clinical", model=GEMMA, student_ref=student_ref):
        return text, False
