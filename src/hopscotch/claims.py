"""Claim readiness for school-based Medicaid.

Districts can bill Medicaid for special education services delivered to eligible
students, and most underclaim heavily. The requirements are the records this
system already governs, so the question is not "what do we have" but "would this
survive an audit".

Published guidance is consistent about what that means:

    Service documentation must tell a consistent story across the IEP, the
    service log, and the claim.

That splits cleanly, and the split is the same one the skill gate makes:

  Rules   -- eligibility, NPI, licence validity, provider type, units against
             documented minutes, service date inside the IEP window. Cheap,
             deterministic, no model.
  Meaning -- does the session note actually describe the service the IEP
             authorizes? Regex cannot answer that. A note reading "worked on
             turn-taking in a small group" against an IEP authorizing INDIVIDUAL
             speech therapy is a real denial, and there is no pattern for it.

Deliberately conservative: this reports what would be denied, and never
generates a claim. Over-claiming is recoupment, and recoupment is worse than
underclaiming.
"""
from __future__ import annotations

from datetime import date

from .schemas import ClaimCheck, ClaimReadiness, IEPService, ServiceDelivery
from .telemetry import span

# One unit is 15 minutes in most state plans. Districts vary; this is the knob.
MINUTES_PER_UNIT = 15


def _rule_checks(
    delivery: ServiceDelivery, authorized: IEPService, *, medicaid_eligible: bool,
    approved_provider_types: set[str],
) -> list[ClaimCheck]:
    c: list[ClaimCheck] = []

    c.append(ClaimCheck(
        requirement="student is Medicaid eligible",
        passed=medicaid_eligible,
        detail="" if medicaid_eligible else "no Medicaid enrollment on file"))

    c.append(ClaimCheck(
        requirement="service authorized in the IEP",
        passed=delivery.goal_ref == authorized.goal_ref,
        detail="" if delivery.goal_ref == authorized.goal_ref
        else f"log cites {delivery.goal_ref}, IEP authorizes {authorized.goal_ref}"))

    in_window = authorized.starts_on <= delivery.service_date <= authorized.ends_on
    c.append(ClaimCheck(
        requirement="delivered inside the IEP effective window",
        passed=in_window,
        detail="" if in_window else
        f"{delivery.service_date} outside {authorized.starts_on}..{authorized.ends_on}"))

    has_npi = bool(delivery.provider_npi.strip())
    c.append(ClaimCheck(
        requirement="provider has an NPI on the log",
        passed=has_npi,
        detail="" if has_npi else "no National Provider Identifier recorded"))

    lic_ok = (delivery.provider_license_expires is not None
              and delivery.provider_license_expires >= delivery.service_date)
    c.append(ClaimCheck(
        requirement="provider licence valid on the service date",
        passed=lic_ok,
        detail="" if lic_ok else
        (f"licence expired {delivery.provider_license_expires}"
         if delivery.provider_license_expires else "no licence expiry recorded")))

    type_ok = delivery.provider_type in approved_provider_types
    c.append(ClaimCheck(
        requirement="approved provider type for this service",
        passed=type_ok,
        detail="" if type_ok else
        f"{delivery.provider_type or 'unrecorded'} not in approved types"))

    # Units against documented minutes. Rounded or estimated entries are among
    # the most frequently cited findings, so an over-bill blocks and an
    # under-bill is flagged as money the district left on the table.
    expected = delivery.minutes // MINUTES_PER_UNIT
    c.append(ClaimCheck(
        requirement="billed units match documented minutes",
        passed=delivery.units_billed == expected,
        blocking=delivery.units_billed > expected,
        detail="" if delivery.units_billed == expected else
        (f"billed {delivery.units_billed} units against {delivery.minutes} min "
         f"(supports {expected}) — OVER-BILLED, recoupment risk"
         if delivery.units_billed > expected else
         f"billed {delivery.units_billed} units against {delivery.minutes} min "
         f"(supports {expected}) — under-billed, revenue left unclaimed")))

    has_note = len(delivery.note.strip()) >= 20
    c.append(ClaimCheck(
        requirement="session note present",
        passed=has_note,
        detail="" if has_note else "note missing or too thin to support a claim"))

    return c


NARRATIVE_PROMPT = """\
You are checking whether one special education session note supports a Medicaid
claim. The test is whether the note and the authorized service tell a consistent
story. An auditor reading both should not find a discrepancy.

Answer with EXACTLY ONE WORD on the first line, then one short sentence:

CONSISTENT   the note describes the authorized service
DISCREPANT   the note describes something materially different -- a different
             modality, a different setting, group where individual was
             authorized, or a service not in the IEP at all
UNCLEAR      the note is too vague to tell either way

Ordinary variation is CONSISTENT. Therapists write informally, and a note that
describes the same service in different words is fine. Reserve DISCREPANT for a
real mismatch an auditor would cite.

AUTHORIZED IN IEP: {service} ({minutes} minutes, {provider_type})
SESSION NOTE ({actual_minutes} minutes):
{note}
"""

_VERDICTS = {"CONSISTENT": True, "DISCREPANT": False, "UNCLEAR": False}


def parse_narrative(text: str) -> tuple[str, str]:
    lines = [l.strip() for l in (text or "").strip().splitlines() if l.strip()]
    if not lines:
        raise ValueError("narrative check returned nothing")
    for i, line in enumerate(lines[:3]):
        token = line.strip().strip('"\'`*#.:').split()[0].upper() if line.split() else ""
        if token in _VERDICTS:
            return token, (lines[i + 1] if len(lines) > i + 1 else "")
    raise ValueError(f"no verdict in narrative output: {text[:120]!r}")


def narrative_check(delivery: ServiceDelivery, authorized: IEPService,
                    *, client=None) -> ClaimCheck:
    """The check rules cannot make. Raises rather than guessing."""
    from google.genai import types

    from .config import FLASH
    from .genai import client as default_client

    c = client or default_client()
    resp = c.models.generate_content(
        model=FLASH,
        contents=NARRATIVE_PROMPT.format(
            service=authorized.service, minutes=authorized.minutes_per_session,
            provider_type=authorized.provider_type,
            actual_minutes=delivery.minutes, note=delivery.note),
        config=types.GenerateContentConfig(
            temperature=0.0, max_output_tokens=200,
            # Gemini 3.x reasons by default and those tokens count against the
            # output cap. At 120 the model spent the entire budget thinking and
            # returned a fragment with finish_reason=MAX_TOKENS -- which read
            # like a parse bug, not a budget one. This is a one-word
            # classification; there is nothing to reason about.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    verdict, reason = parse_narrative(resp.text)
    # UNCLEAR blocks as well as DISCREPANT. A note too vague to tell whether it
    # matches the IEP is the "incomplete documentation" denial -- if an auditor
    # cannot follow the story, the claim does not survive. Conservative on
    # purpose: recoupment is worse than the underclaiming this exists to fix.
    return ClaimCheck(
        requirement="note is consistent with the authorized service",
        passed=_VERDICTS[verdict],
        blocking=(verdict != "CONSISTENT"),
        detail=f"{verdict.lower()}: {reason}" if not _VERDICTS[verdict] else "")


def assess(
    delivery: ServiceDelivery, authorized: IEPService, *,
    medicaid_eligible: bool, approved_provider_types: set[str] | None = None,
    client=None, require_narrative: bool = True,
) -> ClaimReadiness:
    """Would this session survive an audit? Reports; never submits."""
    types_ok = approved_provider_types or {
        "speech-language pathologist", "occupational therapist",
        "physical therapist", "school psychologist", "school social worker"}

    with span("claims.assess", student_ref=delivery.student_ref) as s:
        checks = _rule_checks(delivery, authorized,
                              medicaid_eligible=medicaid_eligible,
                              approved_provider_types=types_ok)
        reviewed = False
        try:
            checks.append(narrative_check(delivery, authorized, client=client))
            reviewed = True
        except Exception as e:
            checks.append(ClaimCheck(
                requirement="note is consistent with the authorized service",
                passed=False, blocking=False,
                detail=f"could not review: {type(e).__name__}"))

        blocking = [c for c in checks if not c.passed and c.blocking]
        # Unchecked is not clean. Same rule as the skill gate.
        billable = not blocking and reviewed

        s.set_attribute("billable", billable)
        s.set_attribute("blocking_failures", len(blocking))
        return ClaimReadiness(
            student_ref=delivery.student_ref, goal_ref=delivery.goal_ref,
            service_date=delivery.service_date, billable=billable,
            checks=checks, reviewed_semantically=reviewed)


# ---------------------------------------------------------------------------
# Batch assessment, for the unattended tick
# ---------------------------------------------------------------------------

MAX_ASSESSMENTS_PER_TICK = 8


def assess_pending(*, store=None, limit: int = MAX_ASSESSMENTS_PER_TICK) -> tuple[int, int]:
    """Assess sessions logged since the last tick. Returns (assessed, billable).

    Marking a session assessed is what makes this idempotent -- a replay finds
    nothing pending rather than re-billing the same model call.
    """
    from . import store as default_store
    store = store or default_store

    pending = store.open_deliveries(limit=limit)
    if not pending:
        return 0, 0

    assessed = billable = 0
    with span("claims.assess_pending", pending=len(pending)):
        for row in pending:
            delivery = ServiceDelivery.model_validate(
                {k: v for k, v in row.items() if k not in ("_id", "assessed", "iep")})
            authorized = IEPService.model_validate(row["iep"])
            r = assess(delivery, authorized,
                       medicaid_eligible=bool(row.get("medicaid_eligible")))
            store.save_readiness(r, delivery_id=row["_id"])
            assessed += 1
            billable += bool(r.billable)
    return assessed, billable
