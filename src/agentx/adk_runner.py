"""Run an ADK agent and get a validated object back.

ADK's run_debug() exists for experimentation and says so in its own docstring.
This uses run_async() -- the documented production path -- because these agents
run unattended in a Cloud Run job where nobody is watching the console.

The agents themselves stay declarative (see agents/); this module owns session
lifecycle and turning an event stream into a typed result.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import TypeVar

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from .config import PROJECT_SLUG
from .supervisor.resilience import with_backoff
from .telemetry import span

T = TypeVar("T", bound=BaseModel)


class AgentRunFailed(RuntimeError):
    """The agent produced nothing usable. Never silently returns a default."""


def _final_payload(events: list) -> str | None:
    """Last text part the agent emitted, walking backwards."""
    for event in reversed(events):
        content = getattr(event, "content", None)
        if content is None:
            continue
        for part in reversed(getattr(content, "parts", None) or []):
            text = getattr(part, "text", None)
            if text and text.strip():
                return text.strip()
    return None


async def _run(agent: LlmAgent, prompt: str, *, user_id: str) -> list:
    runner = InMemoryRunner(agent=agent, app_name=PROJECT_SLUG)
    session = await runner.session_service.create_session(
        app_name=PROJECT_SLUG, user_id=user_id)
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    events = []
    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=message
    ):
        events.append(event)
    return events


def run_structured(agent: LlmAgent, prompt: str, model_cls: type[T], *,
                   user_id: str | None = None) -> T:
    """Invoke `agent` and validate its output into `model_cls`.

    Raises rather than returning a partially-filled object. A half-extracted
    consent form that looks complete is worse than one that failed loudly --
    the whole point downstream is that a wrong date starts a legal clock at the
    wrong moment.
    """
    user_id = user_id or f"batch-{uuid.uuid4().hex[:8]}"
    with span("adk.run", agent=agent.name, model=str(agent.model)):
        # A batch sweep will hit 429 on Vertex's per-minute quota. ADK wraps it
        # as _ResourceExhaustedError; is_transient matches on the message.
        events = with_backoff(lambda: asyncio.run(_run(agent, prompt, user_id=user_id)))
        raw = _final_payload(events)
        if not raw:
            raise AgentRunFailed(f"{agent.name} returned no content")
        try:
            return model_cls.model_validate_json(raw)
        except Exception:
            # output_schema agents sometimes fence their JSON in markdown.
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            try:
                return model_cls.model_validate(json.loads(cleaned))
            except Exception as e:
                raise AgentRunFailed(
                    f"{agent.name} output did not validate as "
                    f"{model_cls.__name__}: {e}; raw={raw[:200]!r}"
                ) from e
