"""The escalation delegation chain.

Every hop crosses a privilege boundary, so the tests are mostly about what
happens when a hop fails. A pipeline that half-succeeds and reports success is
how a family gets a notice containing a test score.
"""
from datetime import date

import pytest

from agentx.deadlines import recompute
from agentx.pipeline import MAX_NOTICES_PER_TICK, PipelineFailed, draft_and_send
from agentx.schemas import Case, CaseStage, ConsentEvent

CLINICAL = "WISC-V FSIQ 87, 19th percentile."


def a_case(ref="stu_0001") -> Case:
    return Case(
        student_ref=ref, school_code="EL-004", jurisdiction="US_FEDERAL",
        stage=CaseStage.CONSENT_RECEIVED,
        consent=ConsentEvent(
            student_ref=ref, school_code="EL-004", jurisdiction="US_FEDERAL",
            consent_signed_on=date(2026, 9, 1), received_on=date(2026, 9, 1),
            referral_reason=CLINICAL, confidence=0.9, source_document="c.pdf"))


def a_comp(case):
    return recompute(case, today=date(2026, 10, 25))


def test_casework_failure_stops_the_chain(monkeypatch):
    """No notice is better than a wrong one. The caller dead-letters."""
    monkeypatch.setattr("agentx.pipeline.run_structured",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("model down")))
    case = a_case()
    with pytest.raises(PipelineFailed, match="casework draft failed"):
        draft_and_send(case, a_comp(case), 7)


def test_redaction_refusal_stops_the_chain(monkeypatch):
    """Gemma unavailable means prepare_handoff refuses. Nothing goes out."""
    from agentx.schemas import DraftedNotice

    monkeypatch.setattr(
        "agentx.pipeline.run_structured",
        lambda agent, prompt, cls, **k: DraftedNotice(
            student_ref="stu_0001", notice_type="prior_written_notice",
            body=CLINICAL, contains_clinical=True))
    monkeypatch.setattr("agentx.guardrails.redact_clinical",
                        lambda text, **kw: (text, False))
    case = a_case()
    with pytest.raises(PipelineFailed, match="redaction gate refused"):
        draft_and_send(case, a_comp(case), 7)


def test_family_agent_is_read_with_the_redacted_scope(monkeypatch):
    """The scope requested is what makes the projection narrow. If someone
    'fixes' a failure by widening it, this fails."""
    from agentx.schemas import DraftedNotice, FamilyPacket

    seen = []

    class SpyGateway:
        def read_case(self, agent, case, *, scope):
            seen.append((agent, scope))
            return {"student_ref": case.student_ref}

    outs = iter([
        DraftedNotice(student_ref="stu_0001", notice_type="prior_written_notice",
                      body="body", contains_clinical=False),
        FamilyPacket(student_ref="stu_0001", language="es-US",
                     letter_text="Estimada familia", redaction_applied=True),
    ])
    monkeypatch.setattr("agentx.pipeline.run_structured",
                        lambda *a, **k: next(outs))
    monkeypatch.setattr("agentx.media.speak",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no creds")))

    case = a_case()
    res = draft_and_send(case, a_comp(case), 7, gateway=SpyGateway())

    assert ("casework-agent", "case.read_full") in seen
    assert ("family-agent", "case.read_redacted") in seen
    assert res.language == "es-US"


def test_missing_audio_degrades_but_does_not_fail(monkeypatch):
    """A missing recording is a degraded notice, not a failed one. The letter
    exists and the deadline is still tracked."""
    from agentx.schemas import DraftedNotice, FamilyPacket

    outs = iter([
        DraftedNotice(student_ref="stu_0001", notice_type="prior_written_notice",
                      body="body", contains_clinical=False),
        FamilyPacket(student_ref="stu_0001", language="en-US",
                     letter_text="Dear family", redaction_applied=True),
    ])
    monkeypatch.setattr("agentx.pipeline.run_structured", lambda *a, **k: next(outs))
    monkeypatch.setattr("agentx.media.speak",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tts down")))

    class OpenGateway:
        def read_case(self, agent, case, *, scope):
            return {"student_ref": case.student_ref}

    case = a_case()
    res = draft_and_send(case, a_comp(case), 7, gateway=OpenGateway())
    assert res.audio_path is None
    assert res.redacted is True


def test_per_tick_cap_is_bounded():
    """Twelve simultaneous escalations would otherwise be ~48 model calls in
    one burst against a per-minute quota."""
    assert 1 <= MAX_NOTICES_PER_TICK <= 10


# --- the daily brief ---------------------------------------------------------

def test_brief_fires_once_per_day_not_once_per_tick():
    """24 ticks a day must not mean 24 briefs."""
    from datetime import date as _date

    from agentx.brief import brief_effect
    from agentx.idempotency import InMemoryLedger

    ledger = InMemoryLedger()
    day = _date(2026, 10, 25)
    assert ledger.claim(brief_effect(day)) is True
    assert ledger.claim(brief_effect(day)) is False
    assert ledger.claim(brief_effect(_date(2026, 10, 26))) is True


def test_caseload_lines_lead_with_urgency():
    """The model gets the most urgent cases, because the list is truncated --
    truncating an unsorted list hides exactly the cases that matter."""
    from datetime import date as _date

    from agentx.brief import MAX_CASES_IN_PROMPT, gather

    class FakeStore:
        def open_cases(self):
            out = []
            for i, days in enumerate([40, -5, 12, 2, 30]):
                c = a_case(f"stu_{i:04d}")
                c.deadline = recompute(c, today=_date(2026, 9, 1))
                c.deadline.days_remaining = days
                out.append(c)
            return out

    lines, _events, n = gather(store=FakeStore(), today=_date(2026, 9, 1))
    assert n == 5
    assert len(lines) <= MAX_CASES_IN_PROMPT
    assert "OVERDUE" in lines[0], "most urgent case is not first"


def test_missing_brief_is_absent_not_invented(monkeypatch):
    """The dashboard shows an honest gap rather than a fabricated summary."""
    import agentx.brief as brief_mod
    monkeypatch.setattr(brief_mod, "latest", lambda: None)
    from agentx.dashboard.app import _brief_html
    assert "No brief yet" in _brief_html()
