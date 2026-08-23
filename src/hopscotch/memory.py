"""Cross-session case memory, backed by Vertex AI Memory Bank.

The tick job is stateless by design -- it wakes, scans, and scales to zero. But
a compliance case runs for months, and the coordinator's real question is never
"what is the deadline" (Firestore has that). It is "what have we already tried,
and who has already been contacted?"

Firestore holds the *facts*. Memory Bank holds the *narrative* across sessions,
so an agent that has never seen a case before still knows the parent was called
twice in October and both times went to voicemail.
"""
from __future__ import annotations

import asyncio
import functools

from google.adk.memory import VertexAiMemoryBankService
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types

from .config import PROJECT_SLUG, settings
from .supervisor.resilience import PermanentFailure
from .telemetry import span


class MemoryUnavailable(PermanentFailure):
    """No agent engine configured. Callers degrade; they never fabricate."""


@functools.lru_cache(maxsize=1)
def service() -> VertexAiMemoryBankService:
    if not settings.agent_engine_id:
        raise MemoryUnavailable(
            "AGENT_ENGINE_ID is unset. Create one with "
            "deploy/create_agent_engine.sh, or run without memory."
        )
    return VertexAiMemoryBankService(
        project=settings.project_id,
        # Memory Bank lives with its Agent Engine instance, which is regional.
        # This is deliberately NOT the model location.
        location=settings.armor_location,
        agent_engine_id=settings.agent_engine_id,
    )


def remember(student_ref: str, text: str, *, author: str) -> None:
    """Record one durable fact about a case."""
    with span("memory.remember", student_ref=student_ref, author=author):
        # The ADK memory service is async; the tick job is a sync batch loop.
        asyncio.run(service().add_memory(
            app_name=PROJECT_SLUG,
            user_id=student_ref,
            memories=[MemoryEntry(
                author=author,
                content=types.Content(role="model", parts=[types.Part(text=text)]),
            )],
        ))


def recall(student_ref: str, query: str) -> list[str]:
    """What do we already know about this case?

    Returns [] when memory is unavailable rather than raising: a missing
    recollection should degrade an agent's context, not fail a statutory
    deadline check that Firestore can answer on its own.
    """
    with span("memory.recall", student_ref=student_ref) as s:
        try:
            resp = asyncio.run(service().search_memory(
                app_name=PROJECT_SLUG, user_id=student_ref, query=query))
        except MemoryUnavailable:
            s.set_attribute("available", False)
            return []
        out = []
        for m in getattr(resp, "memories", []) or []:
            for part in getattr(getattr(m, "content", None), "parts", []) or []:
                if getattr(part, "text", None):
                    out.append(part.text)
        s.set_attribute("hits", len(out))
        return out
