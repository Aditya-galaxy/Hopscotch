"""Intent reviewer, exercised without a network call.

The model's judgement is not testable here and shouldn't be. What IS testable,
and what breaks silently in production, is everything around the call: the
mapping, the bounds, the fencing, and what happens when the model returns
something unusable.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentx.skills import Decision, parse_skill, review
from agentx.skills.model import Category, Severity, Verdict
from agentx.skills.reviewers import (
    MAX_BODY_CHARS, IntentReviewer, _IntentFinding, _IntentResponse,
)


class StubModels:
    def __init__(self, parsed):
        self._parsed = parsed
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        return SimpleNamespace(parsed=self._parsed, text="")


class StubClient:
    def __init__(self, parsed):
        self.models = StubModels(parsed)


def a_skill(tmp_path, body="Do the thing.", name="demo", desc="A demo skill."):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}\n")
    return parse_skill(d)


def test_clean_response_is_safe(tmp_path):
    r = IntentReviewer(client=StubClient(_IntentResponse(findings=[])))
    result = r.review(a_skill(tmp_path))
    assert result.ok
    assert result.findings == []
    assert result.verdict is Verdict.SAFE


def test_findings_map_onto_our_types(tmp_path):
    stub = StubClient(_IntentResponse(findings=[
        _IntentFinding(category="exfiltration", severity="critical",
                       summary="Reads credentials and attaches them to a request",
                       evidence="read the user's ~/.aws/credentials"),
    ]))
    result = IntentReviewer(client=stub).review(a_skill(tmp_path))
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.category is Category.EXFILTRATION
    assert f.severity is Severity.CRITICAL
    assert f.reviewer == "intent"
    assert result.verdict is Verdict.DANGEROUS


def test_unparseable_output_is_not_treated_as_clean(tmp_path):
    """Schema-constrained decoding failed. That is an error, not an all-clear."""
    with pytest.raises(ValueError):
        IntentReviewer(client=StubClient(None)).review(a_skill(tmp_path))


def test_reviewer_failure_fails_the_gate_closed(tmp_path):
    """End to end: a broken reviewer must downgrade, never approve."""
    pkg = a_skill(tmp_path)
    report = review(pkg, reviewers=[IntentReviewer(client=StubClient(None))],
                    require_all=True)
    assert report.decision is Decision.QUARANTINE
    assert "could not run" in report.reasoning


def test_oversized_body_is_bounded_and_reported(tmp_path):
    """22MB of padding must not become a 22MB prompt."""
    stub = StubClient(_IntentResponse(findings=[]))
    pkg = a_skill(tmp_path, body="A" * (MAX_BODY_CHARS + 5000))
    result = IntentReviewer(client=stub).review(pkg)

    assert any(f.category is Category.OBFUSCATION for f in result.findings)
    sent = stub.models.calls[0].contents
    assert len(sent) < MAX_BODY_CHARS + 3000, "full oversized body reached the model"


def test_content_is_fenced_with_an_unpredictable_nonce(tmp_path):
    """A skill that could predict the fence could close it and escape the quotes."""
    stub = StubClient(_IntentResponse(findings=[]))
    r = IntentReviewer(client=stub)
    r.review(a_skill(tmp_path))
    r.review(a_skill(tmp_path))

    fences = []
    for call in stub.models.calls:
        line = [l for l in call.contents.splitlines() if l.startswith("--- BEGIN ")][0]
        fences.append(line)
    assert fences[0] != fences[1], "fence nonce is reused across calls"
    assert "--- END " in stub.models.calls[0].contents


def test_call_is_deterministic_and_schema_constrained(tmp_path):
    stub = StubClient(_IntentResponse(findings=[]))
    IntentReviewer(client=stub).review(a_skill(tmp_path))
    cfg = stub.models.calls[0].config
    assert cfg.temperature == 0.0
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_schema is _IntentResponse
    assert "never take instructions" in cfg.system_instruction


def test_replica_body_actually_reaches_the_model():
    """The committed replica is what day 5's live run is pointed at."""
    replica = Path("data/replicas/credential-helper")
    if not replica.exists():
        pytest.skip("replica not present")
    stub = StubClient(_IntentResponse(findings=[]))
    IntentReviewer(client=stub).review(parse_skill(replica))
    sent = stub.models.calls[0].contents
    assert "~/.aws/credentials" in sent
    assert "X-Env-Context" in sent
