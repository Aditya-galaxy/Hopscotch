"""The morning brief.

Everything else in this system is the fleet acting. This is the fleet
*reporting* -- the difference between a dashboard a coordinator has to read and
an assistant that tells them what happened.

It runs once a day, claimed through the same idempotency ledger as everything
else, and it is the only place the supervisor model is used for something other
than adjudicating a failure. That is deliberate: summarising a caseload is
exactly the judgement call worth paying Pro for, and it happens once per day
rather than once per case.
"""
from __future__ import annotations

from datetime import date

import logging

from .config import PROJECT_SLUG, settings
from .idempotency import effect_id
from .schemas import Case, DailyBrief
from .telemetry import span

log = logging.getLogger(PROJECT_SLUG)

MAX_CASES_IN_PROMPT = 25
MAX_EVENTS_IN_PROMPT = 20


def brief_effect(day: date) -> str:
    """One brief per day, ever. A second tick in the same day is a no-op."""
    return effect_id("daily_brief", day.isoformat())


def _case_line(c: Case) -> str:
    d = c.deadline
    if d is None:
        return f"{c.student_ref} ({c.school_code}): no clock — intake incomplete"
    sent = ", ".join(f"T-{r}" for r in sorted(c.escalations_sent, reverse=True)) or "none"
    state = "OVERDUE by" if d.days_remaining < 0 else "due in"
    return (f"{c.student_ref} ({c.school_code}, {c.jurisdiction}): "
            f"{state} {abs(d.days_remaining)}d on {d.due_on.isoformat()}; "
            f"notices sent: {sent}")


def gather(*, store=None, today: date | None = None) -> tuple[list[str], list[str], int]:
    """Caseload lines and recent events, both bounded.

    Sorted by urgency and truncated rather than summarised, because a brief
    built from a summary of a summary loses the specifics a coordinator needs
    to actually act.
    """
    from . import store as default_store
    from .config import settings
    from .store import client_kwargs

    store = store or default_store
    today = today or date.today()

    cases = list(store.open_cases())
    cases.sort(key=lambda c: c.deadline.days_remaining if c.deadline else 9999)
    lines = [_case_line(c) for c in cases[:MAX_CASES_IN_PROMPT]]

    events: list[str] = []
    try:
        from google.cloud import firestore
        db = firestore.Client(**client_kwargs())
        rows = [d.to_dict() for d in
                db.collection(settings.audit_collection).limit(200).stream()]
        rows.sort(key=lambda r: r.get("at", ""), reverse=True)
        for r in rows[:MAX_EVENTS_IN_PROMPT]:
            events.append(
                f"{(r.get('at') or '')[:16]} {r.get('event')} "
                f"{r.get('student_ref') or r.get('agent') or ''} "
                f"{r.get('rung') or r.get('scope') or ''}".strip())
    except Exception:
        pass  # a brief without event history is degraded, not broken

    return lines, events, len(cases)


PROMPT = """\
Write today's brief for a special education compliance coordinator who has
three hundred other things to do.

Rules:
- `headline` is one sentence. If they read nothing else, what do they need?
- `needs_you_today` is only what a HUMAN must do. The fleet already sends
  notices; do not list those. Overdue cases, failed notices, and incomplete
  intake belong here.
- `moved_overnight` is what the fleet did unattended. Be specific and brief.
- `watch` is not urgent yet but will be within a week.
- Use student references exactly as given. Never invent a case, a date, or a
  number. If a list is empty, leave it empty — do not pad it.
- No preamble, no encouragement, no restating the question.

TODAY: {today}
OPEN CASES: {n}

CASELOAD (most urgent first):
{cases}

RECENT ACTIVITY:
{events}
"""


def _remote_brief(prompt: str) -> DailyBrief | None:
    """Ask the supervisor deployed on Agent Engine Runtime.

    Returns None when no runtime is configured, so the local ADK path stays the
    default and nothing depends on a managed service being reachable.
    """
    import json
    import os

    engine_id = os.environ.get("AGENT_ENGINE_RUNTIME", "")
    if not engine_id:
        return None

    import vertexai
    from vertexai import agent_engines

    vertexai.init(project=settings.project_id, location=settings.armor_location)
    remote = agent_engines.get(
        f"projects/{settings.project_id}/locations/{settings.armor_location}"
        f"/reasoningEngines/{engine_id}")

    text = ""
    for ev in remote.stream_query(message=prompt, user_id="tick"):
        if ev.get("error_code"):
            raise RuntimeError(f"agent engine: {str(ev.get('error_message'))[:200]}")
        for part in (ev.get("content") or {}).get("parts") or []:
            text += part.get("text") or ""
    raw = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return DailyBrief.model_validate(json.loads(raw))


def generate(*, today: date | None = None, store=None) -> DailyBrief:
    """Compose the brief. Raises if the model is unreachable — the caller
    treats a missing brief as a missing brief, not an empty one."""
    from .adk_runner import run_structured
    from .agents.coordinator import coordinator

    today = today or date.today()
    with span("brief.generate", day=today.isoformat()) as s:
        cases, events, n_open = gather(store=store, today=today)
        prompt = PROMPT.format(
            today=today.isoformat(), n=n_open,
            cases="\n".join(cases) or "(none)",
            events="\n".join(events) or "(none recorded)")
        try:
            brief = _remote_brief(prompt)
            s.set_attribute("runtime", "agent_engine" if brief else "local")
        except Exception as e:
            log.warning("agent engine unavailable, running locally: %s: %s",
                        type(e).__name__, str(e)[:160])
            s.set_attribute("runtime", "local_fallback")
            brief = None
        if brief is None:
            brief = run_structured(coordinator, prompt, DailyBrief)

        brief.brief_date = today.isoformat()
        brief.cases_open = n_open
        s.set_attribute("needs_you", len(brief.needs_you_today))
        return brief


def save(brief: DailyBrief) -> None:
    from google.cloud import firestore

    from .store import _client, client_kwargs  # noqa: F401
    db = firestore.Client(**client_kwargs())
    db.collection("briefs").document(brief.brief_date).set(
        brief.model_dump(mode="json"))


def latest() -> DailyBrief | None:
    """Most recent brief, for the dashboard. None rather than a fabricated one.

    The failure here is LOGGED, not swallowed. A bare `except Exception: return
    None` hid a NameError in this function for four days: `client_kwargs` was
    imported inside one function and used in three, so both save() and latest()
    raised. The dashboard reported "No brief yet" while four briefs sat in
    Firestore, and the daily brief -- the thing the supervisor exists to produce
    -- silently stopped being written on 25 Aug. "No data" and "this code is
    broken" must not look the same from the outside.
    """
    from google.cloud import firestore

    from .store import client_kwargs
    try:
        db = firestore.Client(**client_kwargs())
        rows = [d.to_dict() for d in db.collection("briefs").limit(30).stream()]
        if not rows:
            return None
        rows.sort(key=lambda r: r.get("brief_date", ""), reverse=True)
        return DailyBrief.model_validate(rows[0])
    except Exception as exc:
        log.warning("brief lookup failed, dashboard will show none: %r", exc)
        return None
