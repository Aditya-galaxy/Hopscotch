"""The escalation pipeline: what actually happens when a deadline gets close.

This is the delegation chain the whole system exists for, and every hop crosses
a privilege boundary:

    clock detects a rung is due
      -> gateway authorizes casework-agent for case.read_full
      -> casework_agent drafts the statutory notice          [LlmAgent, Flash]
      -> Gemma strips every clinical finding
      -> gateway projects a REDACTED view for family-agent
      -> family_agent writes the parent letter                [LlmAgent, Flash]
      -> Chirp speaks it in the family's language
      -> Memory Bank records what was sent

casework-agent holds the clinical narrative and can do almost nothing else.
family-agent reaches the outside world and never sees clinical text -- not
because it declines to, but because the gateway never hands it any.

Bounded on purpose: a tick that fires twelve escalations would otherwise make
~48 model calls in one burst against a per-minute quota. Work above the cap
rolls to the next hour, which is fine -- these are 14, 7 and 2 day warnings,
not pages.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .adk_runner import run_structured
from .config import PROJECT_SLUG
from .schemas import Case, DeadlineComputation, DraftedNotice, FamilyPacket
from .telemetry import span

log = logging.getLogger(PROJECT_SLUG)

MAX_NOTICES_PER_TICK = 5


@dataclass
class NoticeResult:
    student_ref: str
    notice_type: str
    language: str
    audio_path: str | None
    redacted: bool


class PipelineFailed(RuntimeError):
    """The chain broke partway. The caller dead-letters so a human drafts it."""


def _casework_prompt(view: dict, comp: DeadlineComputation, rung: int) -> str:
    return (
        f"Draft a Prior Written Notice for an approaching evaluation deadline.\n\n"
        f"Days remaining: {comp.days_remaining} (T-{rung} warning)\n"
        f"Statutory deadline: {comp.due_on.isoformat()}\n"
        f"Rule applied: {comp.rule_label}\n"
        f"How the date was computed: {comp.explanation}\n\n"
        f"Case record:\n{view}\n"
    )


def _family_prompt(view: dict, redacted_body: str) -> str:
    return (
        "Rewrite this notice as a letter a parent will actually read.\n\n"
        "The clinical content has already been removed upstream. If you still "
        "see a diagnosis, test name, or score, stop and say so rather than "
        "paraphrasing it.\n\n"
        "Choose `language` from the family's record if present, otherwise "
        "'en-US'. Set redaction_applied to true. Use the student_ref exactly "
        "as given.\n\n"
        f"Case record (redacted):\n{view}\n\nNotice:\n{redacted_body}\n"
    )


def draft_and_send(
    case: Case, comp: DeadlineComputation, rung: int, *, gateway=None,
) -> NoticeResult:
    """Run the full chain for one escalation. Raises PipelineFailed on any hop."""
    from .agents.casework import casework_agent
    from .agents.family import family_agent, prepare_handoff
    from .gateway import Gateway

    gw = gateway or Gateway()

    with span("pipeline.escalation", student_ref=case.student_ref, rung=rung) as s:
        try:
            # casework-agent: full clinical access, narrowest tools.
            full_view = gw.read_case("casework-agent", case, scope="case.read_full")
            notice = run_structured(
                casework_agent, _casework_prompt(full_view, comp, rung), DraftedNotice)
        except Exception as e:
            raise PipelineFailed(f"casework draft failed: {type(e).__name__}: {e}") from e

        # Gemma strips clinical content. Fails closed -- prepare_handoff raises
        # rather than letting an unredacted notice reach a family.
        try:
            redacted_body = prepare_handoff(notice)
        except PermissionError as e:
            raise PipelineFailed(f"redaction gate refused: {e}") from e

        try:
            # family-agent: redacted projection only. It cannot ask for more.
            fam_view = gw.read_case("family-agent", case, scope="case.read_redacted")
            packet = run_structured(
                family_agent, _family_prompt(fam_view, redacted_body), FamilyPacket)
        except Exception as e:
            raise PipelineFailed(f"family letter failed: {type(e).__name__}: {e}") from e

        audio: Path | None = None
        try:
            from .media import speak
            audio = speak(packet.letter_text, language=packet.language or "en-US")
        except Exception as e:
            # A missing recording is a degraded notice, not a failed one -- the
            # letter exists and the deadline is still tracked. But LOG it: a
            # span attribute nobody reads is the same as swallowing it, which
            # is how the missing aiplatform dependency hid for a whole deploy.
            s.set_attribute("audio_error", type(e).__name__)
            log.warning("audio skipped for %s: %s: %s",
                        case.student_ref, type(e).__name__, str(e)[:200])

        s.set_attribute("language", packet.language or "en-US")
        s.set_attribute("audio", bool(audio))
        return NoticeResult(
            student_ref=case.student_ref, notice_type=notice.notice_type,
            language=packet.language or "en-US",
            audio_path=str(audio) if audio else None,
            redacted=packet.redaction_applied,
        )
