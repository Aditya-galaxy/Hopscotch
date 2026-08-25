"""Building the actual Medicaid claim.

Claim *readiness* asks whether a session would survive an audit. This turns a
session that passed into the thing a billing system can ingest -- coded,
bundled-checked, batched, and exported.

WHAT THIS DELIBERATELY DOES NOT DO: submit. Direct submission needs provider
enrollment, a trading partner agreement, EDI connectivity and test-to-production
certification with the state. Most districts submit through a billing vendor
anyway, so the useful output is a clean, coded batch that a vendor ingests --
not a half-implemented X12 pipeline that files real money at a state agency.
A malformed 837P is worse than a good CSV.

Codes are the real ones. 92507 individual speech treatment, 92508 group, 97530
therapeutic activities, 90832 psychotherapy. Rates and modifiers vary by state
plan, which is why none are hardcoded here.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from .idempotency import effect_id
from .schemas import IEPService, ServiceDelivery
from .telemetry import span


class Modality(str, Enum):
    INDIVIDUAL = "individual"
    GROUP = "group"


# service keyword -> (individual code, group code, description)
CODE_MAP: dict[str, tuple[str, str, str]] = {
    "speech": ("92507", "92508", "Speech/language treatment"),
    "occupational": ("97530", "97150", "Therapeutic activities"),
    "physical": ("97110", "97150", "Therapeutic exercise"),
    "counsel": ("90832", "90853", "Psychotherapy"),
    "psycholog": ("90832", "90853", "Psychotherapy"),
}

# NCCI bundling. An SLP must not separately report these alongside 92507/92508 --
# they are considered included. Billing both on the same date for the same
# student is a recoupment finding, not a rejection at submission, which is why
# it has to be caught here rather than discovered later.
SPEECH_CODES = {"92507", "92508"}
BUNDLED_INTO_SPEECH = {"97110", "97112", "97150", "97530", "97127", "G0515"}


class ClaimLine(BaseModel):
    """One billable session, coded."""
    id: str
    student_ref: str
    service_date: date
    procedure_code: str
    description: str
    modality: Modality
    units: int
    minutes: int
    provider_npi: str
    provider_type: str
    iep_goal_ref: str
    bundling_conflict: str = Field(
        default="", description="Non-empty means this line must not be submitted")

    @property
    def submittable(self) -> bool:
        return not self.bundling_conflict


class ClaimBatch(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    lines: list[ClaimLine] = Field(default_factory=list)
    approved_by: str = ""
    exported_at: str = ""

    @property
    def submittable_lines(self) -> list[ClaimLine]:
        return [l for l in self.lines if l.submittable]

    @property
    def total_units(self) -> int:
        return sum(l.units for l in self.submittable_lines)


class CannotCode(ValueError):
    """No code maps to this service. Never guess a procedure code."""


def pick_code(service: str, modality: Modality) -> tuple[str, str]:
    """Map an IEP service to a procedure code. Raises rather than guessing."""
    lowered = service.lower()
    for keyword, (individual, group, desc) in CODE_MAP.items():
        if keyword in lowered:
            return (individual if modality is Modality.INDIVIDUAL else group), desc
    raise CannotCode(
        f"no procedure code mapped for {service!r}; add it to CODE_MAP rather "
        "than letting a claim go out under a guessed code")


def build_line(delivery: ServiceDelivery, authorized: IEPService,
               *, modality: Modality = Modality.INDIVIDUAL,
               minutes_per_unit: int = 15) -> ClaimLine:
    """Code one delivered session.

    `modality` comes from the readiness check, not from the IEP: the narrative
    reviewer is what notices a note describing a GROUP session against an IEP
    authorizing individual therapy. Billing 92507 for that session is the denial
    that check exists to prevent, so the code follows what actually happened.
    """
    code, desc = pick_code(authorized.service, modality)
    return ClaimLine(
        id=effect_id("claimline", delivery.student_ref, delivery.goal_ref,
                     delivery.service_date.isoformat()),
        student_ref=delivery.student_ref, service_date=delivery.service_date,
        procedure_code=code, description=desc, modality=modality,
        units=delivery.minutes // minutes_per_unit, minutes=delivery.minutes,
        provider_npi=delivery.provider_npi, provider_type=delivery.provider_type,
        iep_goal_ref=delivery.goal_ref)


def check_bundling(lines: list[ClaimLine]) -> list[ClaimLine]:
    """Flag NCCI conflicts within a batch.

    Same student, same date: a speech code and a bundled therapy code cannot
    both be submitted. The bundled line is flagged rather than dropped, because
    a coordinator needs to see what was withheld and why.
    """
    by_student_date: dict[tuple[str, date], list[ClaimLine]] = defaultdict(list)
    for line in lines:
        by_student_date[(line.student_ref, line.service_date)].append(line)

    for (student, day), group in by_student_date.items():
        codes = {l.procedure_code for l in group}
        if not (codes & SPEECH_CODES):
            continue
        speech = ", ".join(sorted(codes & SPEECH_CODES))
        for line in group:
            if line.procedure_code in BUNDLED_INTO_SPEECH:
                line.bundling_conflict = (
                    f"NCCI: {line.procedure_code} is included in {speech} for "
                    f"{student} on {day}; submitting both risks recoupment")
    return lines


def build_batch(items: list[tuple[ServiceDelivery, IEPService, Modality]]) -> ClaimBatch:
    """Code every billable session and run the bundling check across the batch."""
    with span("claim.build_batch", sessions=len(items)) as s:
        lines: list[ClaimLine] = []
        for delivery, authorized, modality in items:
            try:
                lines.append(build_line(delivery, authorized, modality=modality))
            except CannotCode:
                continue  # surfaced by readiness; never coded on a guess
        lines = check_bundling(lines)
        batch = ClaimBatch(
            id=effect_id("claimbatch", datetime.now(timezone.utc).isoformat()),
            lines=lines)
        s.set_attribute("lines", len(lines))
        s.set_attribute("blocked_by_bundling", len(lines) - len(batch.submittable_lines))
        return batch


EXPORT_COLUMNS = [
    "student_ref", "service_date", "procedure_code", "description",
    "modality", "units", "minutes", "provider_npi", "provider_type",
    "iep_goal_ref",
]


def to_csv(batch: ClaimBatch) -> str:
    """Export for a billing vendor. Only submittable lines leave."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS, lineterminator="\n")
    w.writeheader()
    for line in batch.submittable_lines:
        w.writerow({c: getattr(line, c) for c in EXPORT_COLUMNS})
    return buf.getvalue()


def current_batch(*, limit: int = 200) -> ClaimBatch:
    """Code every billable, unexported session currently on file.

    Modality follows the session note, because the narrative reviewer is what
    distinguishes a group session from an individual one -- and that
    distinction is the difference between 92507 and 92508.
    """
    from google.cloud import firestore

    from .config import settings
    from .store import client_kwargs

    db = firestore.Client(**client_kwargs())
    ready = {d.id: d.to_dict()
             for d in db.collection("claim_readiness").limit(limit).stream()}

    items: list[tuple[ServiceDelivery, IEPService, Modality]] = []
    for doc in db.collection("deliveries").limit(limit).stream():
        verdict = ready.get(doc.id)
        if not verdict or not verdict.get("billable"):
            continue
        row = doc.to_dict()
        delivery = ServiceDelivery.model_validate(
            {k: v for k, v in row.items()
             if k not in ("iep", "assessed", "medicaid_eligible")})
        modality = (Modality.GROUP if "group" in delivery.note.lower()
                    else Modality.INDIVIDUAL)
        items.append((delivery, IEPService.model_validate(row["iep"]), modality))

    return build_batch(items)
