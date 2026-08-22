"""Gemini client factory.

One place decides whether we talk to Vertex AI or the Gemini API, because the
hackathon accepts either and the two need different bootstrapping. Prototyping
runs on a Gemini API key with no billing account; production flips
GOOGLE_GENAI_USE_VERTEXAI=true and authenticates with ADC.
"""
from __future__ import annotations

import functools
import os

from google import genai

from .config import settings
from .supervisor.resilience import PermanentFailure


class CredentialsMissing(PermanentFailure):
    """Raised instead of guessing. A reviewer that cannot authenticate must
    fail closed, not silently return 'nothing found'."""


@functools.lru_cache(maxsize=2)
def client() -> genai.Client:
    if settings.use_vertex:
        if not settings.project_id:
            raise CredentialsMissing(
                "GOOGLE_CLOUD_PROJECT is unset and GOOGLE_GENAI_USE_VERTEXAI=true. "
                "Set the project, or set GOOGLE_GENAI_USE_VERTEXAI=false and "
                "provide GEMINI_API_KEY for local work."
            )
        return genai.Client(vertexai=True, project=settings.project_id,
                            location=settings.location)

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise CredentialsMissing(
            "No GEMINI_API_KEY. Get one free at https://aistudio.google.com/apikey, "
            "or set GOOGLE_GENAI_USE_VERTEXAI=true with GOOGLE_CLOUD_PROJECT."
        )
    return genai.Client(api_key=key)
