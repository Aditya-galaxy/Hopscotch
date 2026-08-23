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


REDACTION_PROMPT = """\
Rewrite this special education notice so a parent can read it, with every
clinical detail removed.

REMOVE: diagnoses, test names, test scores, percentiles, standard scores,
clinical observations, and any professional's assessment of the child.

KEEP: what the district will do, what the family can do, dates and deadlines,
who to contact, and the child's name or reference.

Do not summarise the clinical content in gentler words -- remove it. "Showed
difficulty with phonological processing" is still a clinical finding when
written kindly.

Return only the rewritten notice. No preamble.

NOTICE:
{text}
"""


def redact_clinical(text: str, *, student_ref: str) -> tuple[str, bool]:
    """Strip clinical findings before the family-facing handoff.

    Runs on Gemma rather than Gemini deliberately. This is a narrow, mechanical
    transformation on every outbound notice, so it belongs on the cheap model --
    and keeping it off the expensive one is what makes running it on *every*
    notice affordable rather than a thing someone later makes conditional.

    Returns (text, redacted). On any failure it returns the ORIGINAL text with
    redacted=False, and the caller refuses the handoff. It never returns text
    it did not successfully process while claiming it did.
    """
    with span("guardrail.redact_clinical", model=GEMMA, student_ref=student_ref) as s:
        try:
            from google.genai import types

            from .genai import client

            resp = client().models.generate_content(
                model=GEMMA,
                contents=REDACTION_PROMPT.format(text=text),
                config=types.GenerateContentConfig(temperature=0.0),
            )
            out = (resp.text or "").strip()
            if not out:
                s.set_attribute("redacted", False)
                return text, False
            s.set_attribute("redacted", True)
            return out, True
        except Exception as e:
            # Fail closed: the caller treats redacted=False as "do not send".
            s.set_attribute("redacted", False)
            s.set_attribute("error", type(e).__name__)
            return text, False
