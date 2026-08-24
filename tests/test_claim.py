"""Claim coding, NCCI bundling, and export.

Readiness decides whether a session survives an audit. This decides what code
goes on the claim, and the codes are real: 92507 individual speech treatment,
92508 group, 97530 therapeutic activities, 90832 psychotherapy.
"""
from datetime import date

import pytest

from hopscotch.claim import (
    BUNDLED_INTO_SPEECH, CannotCode, Modality, build_batch, build_line,
    check_bundling, pick_code, to_csv,
)
from hopscotch.schemas import IEPService, ServiceDelivery

SPEECH_IEP = IEPService(
    goal_ref="G-3", service="speech-language therapy, individual",
    minutes_per_session=30, sessions_per_week=2,
    provider_type="speech-language pathologist",
    starts_on=date(2026, 9, 1), ends_on=date(2027, 6, 30))

OT_IEP = SPEECH_IEP.model_copy(update={
    "goal_ref": "G-4", "service": "occupational therapy, individual",
    "provider_type": "occupational therapist"})


def delivery(ref="stu_0001", goal="G-3", day=date(2026, 10, 6), minutes=30):
    return ServiceDelivery(
        student_ref=ref, goal_ref=goal, service_date=day, minutes=minutes,
        units_billed=minutes // 15, note="Session note.",
        provider_npi="1234567890", provider_type="speech-language pathologist",
        provider_license_expires=date(2027, 12, 31))


# --- coding ------------------------------------------------------------------

def test_individual_and_group_speech_are_different_codes():
    assert pick_code("speech-language therapy, individual", Modality.INDIVIDUAL)[0] == "92507"
    assert pick_code("speech-language therapy, individual", Modality.GROUP)[0] == "92508"


def test_modality_follows_what_happened_not_what_was_authorized():
    """The narrative reviewer is what notices a note describing a GROUP session
    against an IEP authorizing individual therapy. Billing 92507 for that
    session is precisely the denial that check exists to prevent, so the code
    follows the delivery."""
    line = build_line(delivery(), SPEECH_IEP, modality=Modality.GROUP)
    assert line.procedure_code == "92508"
    assert line.modality is Modality.GROUP


def test_an_unmapped_service_raises_rather_than_guessing():
    """A guessed procedure code is a false claim."""
    weird = SPEECH_IEP.model_copy(update={"service": "equine-assisted learning"})
    with pytest.raises(CannotCode, match="no procedure code mapped"):
        build_line(delivery(), weird)


def test_units_derive_from_documented_minutes():
    assert build_line(delivery(minutes=45), SPEECH_IEP).units == 3
    assert build_line(delivery(minutes=30), SPEECH_IEP).units == 2


# --- NCCI bundling -----------------------------------------------------------

def test_therapy_bundled_into_speech_on_the_same_day_is_blocked():
    """An SLP must not separately report 97530 alongside 92507 -- it is
    considered included. Billing both is a recoupment finding, not a rejection
    at submission, so it has to be caught before export."""
    speech = build_line(delivery(goal="G-3"), SPEECH_IEP)
    ot = build_line(delivery(goal="G-4"), OT_IEP)
    assert ot.procedure_code in BUNDLED_INTO_SPEECH

    check_bundling([speech, ot])
    assert speech.submittable, "the speech line should still go"
    assert not ot.submittable
    assert "NCCI" in ot.bundling_conflict
    assert "92507" in ot.bundling_conflict


def test_bundling_is_scoped_to_the_same_student_and_day():
    speech = build_line(delivery(ref="stu_0001"), SPEECH_IEP)
    ot_other_student = build_line(delivery(ref="stu_0002", goal="G-4"), OT_IEP)
    ot_other_day = build_line(
        delivery(ref="stu_0001", goal="G-4", day=date(2026, 10, 7)), OT_IEP)

    check_bundling([speech, ot_other_student, ot_other_day])
    assert ot_other_student.submittable, "a different student was blocked"
    assert ot_other_day.submittable, "a different date was blocked"


def test_a_conflicted_line_is_flagged_not_dropped():
    """A coordinator needs to see what was withheld and why."""
    batch = build_batch([
        (delivery(goal="G-3"), SPEECH_IEP, Modality.INDIVIDUAL),
        (delivery(goal="G-4"), OT_IEP, Modality.INDIVIDUAL)])
    assert len(batch.lines) == 2
    assert len(batch.submittable_lines) == 1


# --- export ------------------------------------------------------------------

def test_only_submittable_lines_are_exported():
    batch = build_batch([
        (delivery(goal="G-3"), SPEECH_IEP, Modality.INDIVIDUAL),
        (delivery(goal="G-4"), OT_IEP, Modality.INDIVIDUAL)])
    csv_out = to_csv(batch)
    assert csv_out.count("\n") == 2, "header plus exactly one line"
    assert "92507" in csv_out
    assert "97530" not in csv_out, "a bundled line reached the export"


def test_export_carries_what_a_billing_vendor_needs():
    batch = build_batch([(delivery(), SPEECH_IEP, Modality.INDIVIDUAL)])
    header = to_csv(batch).splitlines()[0]
    for column in ("student_ref", "service_date", "procedure_code", "units",
                   "provider_npi", "iep_goal_ref"):
        assert column in header, f"{column} missing from the export"


def test_line_ids_are_stable_so_a_rerun_does_not_duplicate():
    a = build_line(delivery(), SPEECH_IEP)
    b = build_line(delivery(), SPEECH_IEP)
    assert a.id == b.id
