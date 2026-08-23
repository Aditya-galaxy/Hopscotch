"""Family-facing output: redaction, voice, and the dashboard's file route.

None of these need credentials. What is tested is the behaviour around the
model calls -- the failure modes, the caching, and the path handling -- because
those are what break silently in production.
"""
from pathlib import Path

import pytest

from hopscotch.dashboard.app import app
from hopscotch.guardrails import redact_clinical
from hopscotch.media import VOICES, speak


def test_redaction_fails_closed_when_the_model_is_unreachable(monkeypatch):
    """Returns the ORIGINAL text with redacted=False, never a partial strip
    labelled as done. The caller refuses the handoff on False."""
    def boom():
        raise RuntimeError("no credentials")
    monkeypatch.setattr("hopscotch.genai.client", boom)

    original = "WISC-V Full Scale IQ of 87 (19th percentile)."
    out, ok = redact_clinical(original, student_ref="stu_0001")
    assert ok is False
    assert out == original, "returned altered text while reporting failure"


def test_family_handoff_refuses_unredacted_clinical_content(monkeypatch):
    """The independent second gate. Even if projection failed upstream, a
    notice flagged clinical does not go out unredacted."""
    from hopscotch.agents.family import prepare_handoff
    from hopscotch.schemas import DraftedNotice

    monkeypatch.setattr("hopscotch.guardrails.redact_clinical",
                        lambda text, **kw: (text, False))
    notice = DraftedNotice(student_ref="stu_0001", notice_type="prior_written_notice",
                           body="Full Scale IQ of 87.", contains_clinical=True)
    with pytest.raises(PermissionError, match="refusing family handoff"):
        prepare_handoff(notice)


def test_every_voice_is_a_chirp3_voice():
    """Chirp3-HD specifically. A silent fallback to a legacy voice would still
    speak, just markedly worse, and nobody would notice."""
    assert VOICES
    for lang, voice in VOICES.items():
        assert "Chirp3-HD" in voice, f"{lang} is not a Chirp3 voice"


def test_audio_is_cached_by_content_not_regenerated(tmp_path, monkeypatch):
    """A tick that re-runs must not re-synthesise the same notice."""
    calls = {"n": 0}

    class FakeClient:
        def synthesize_speech(self, **kw):
            calls["n"] += 1
            return type("R", (), {"audio_content": b"ID3fake"})()

    import hopscotch.media as media
    monkeypatch.setattr(media, "MEDIA_DIR", tmp_path)
    monkeypatch.setitem(__import__("sys").modules, "google.cloud.texttospeech",
                        __import__("google.cloud.texttospeech", fromlist=["x"]))
    monkeypatch.setattr(
        "google.cloud.texttospeech.TextToSpeechClient", lambda **kw: FakeClient())

    p1 = speak("hello", language="en-US")
    p2 = speak("hello", language="en-US")
    assert p1 == p2
    assert calls["n"] == 1, "regenerated identical audio"


def test_media_route_refuses_path_traversal():
    """The dashboard serves files from a directory; it must not serve files
    from above it."""
    from fastapi.testclient import TestClient
    c = TestClient(app)
    for bad in ("../../etc/passwd", "..%2F..%2Fetc%2Fpasswd"):
        assert c.get(f"/media/{bad}").status_code in (404, 400)


def test_dashboard_health_needs_no_cloud():
    from fastapi.testclient import TestClient
    assert TestClient(app).get("/healthz").json() == {"ok": True}
