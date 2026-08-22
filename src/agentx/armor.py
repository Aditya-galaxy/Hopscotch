"""Model Armor boundary.

One module, two subjects. The same inline guardrail screens a scanned
evaluation that arrived from a parent's phone and a SKILL.md the agent is about
to absorb as a permanent capability. Both are text that entered from outside
the trust boundary and both can carry instructions aimed at the model.

The template is infrastructure, created once by deploy/, not per call.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass

from google.api_core.client_options import ClientOptions
from google.cloud import modelarmor_v1 as ma

from .config import settings
from .supervisor.resilience import PermanentFailure
from .telemetry import span

TEMPLATE_ID = "agentx-skill-review"


class ArmorUnavailable(PermanentFailure):
    """No template configured. Callers must fail closed, never assume clean."""


@functools.lru_cache(maxsize=1)
def _client() -> ma.ModelArmorClient:
    # Model Armor is regional and needs its explicit regional endpoint; the
    # default global host will not resolve the template.
    return ma.ModelArmorClient(client_options=ClientOptions(
        api_endpoint=f"modelarmor.{settings.armor_location}.rep.googleapis.com"))


def template_name() -> str:
    if not settings.project_id:
        raise ArmorUnavailable("GOOGLE_CLOUD_PROJECT is unset")
    tpl = settings.armor_template or TEMPLATE_ID
    return (f"projects/{settings.project_id}/locations/{settings.armor_location}"
            f"/templates/{tpl}")


@dataclass(frozen=True)
class ArmorFinding:
    filter_name: str
    confidence: str          # "" when the filter reports no confidence band
    detail: str


@dataclass(frozen=True)
class ArmorResult:
    matched: bool
    findings: tuple[ArmorFinding, ...]

    @property
    def worst_confidence(self) -> str:
        order = {"LOW_AND_ABOVE": 1, "MEDIUM_AND_ABOVE": 2, "HIGH": 3}
        best = max((f.confidence for f in self.findings),
                   key=lambda c: order.get(c, 0), default="")
        return best


def screen(text: str, *, subject: str) -> ArmorResult:
    """Screen untrusted text. Raises rather than returning a false all-clear."""
    with span("armor.screen", subject=subject, chars=len(text)) as s:
        resp = _client().sanitize_user_prompt(
            request=ma.SanitizeUserPromptRequest(
                name=template_name(), user_prompt_data=ma.DataItem(text=text)))
        result = resp.sanitization_result
        findings: list[ArmorFinding] = []
        for key, fr in result.filter_results.items():
            for attr in ("pi_and_jailbreak_filter_result",
                         "malicious_uri_filter_result",
                         "sdp_filter_result", "rai_filter_result"):
                sub = getattr(fr, attr, None)
                if sub is None:
                    continue
                state = getattr(sub, "match_state", None)
                if state is None or state.name != "MATCH_FOUND":
                    continue
                conf = getattr(sub, "confidence_level", None)
                findings.append(ArmorFinding(
                    filter_name=key,
                    confidence=conf.name if conf else "",
                    detail=attr.replace("_filter_result", ""),
                ))
        matched = result.filter_match_state.name == "MATCH_FOUND"
        s.set_attribute("matched", matched)
        s.set_attribute("findings", len(findings))
        return ArmorResult(matched=matched, findings=tuple(findings))
