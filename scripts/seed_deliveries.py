"""Seed synthetic service delivery logs so claim readiness has something to do.

Deliberately imperfect, in the proportions real districts see. Published audit
findings put credentialing lapses, time-based errors and IEP/log mismatches at
the top of denial reasons, so the corpus contains all three -- plus a majority
of clean sessions, because a corpus of only broken ones would let a gate that
flags everything look good.
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta

from hopscotch import store
from hopscotch.schemas import IEPService, ServiceDelivery

SERVICES = [
    ("speech-language therapy, individual", "speech-language pathologist", 30,
     "Individual session. Targeted /r/ in structured phrases, {p}% accuracy "
     "with minimal cueing."),
    ("occupational therapy, individual", "occupational therapist", 30,
     "Individual OT. Worked on bilateral coordination and pencil grip; "
     "{p}% independence on fastener tasks."),
    ("counselling, individual", "school social worker", 30,
     "Individual check-in. Practised self-regulation strategies; student "
     "identified two triggers independently."),
]
# The mismatch a rule check cannot catch: a group note against an IEP that
# authorizes individual therapy.
GROUP_NOTE = ("Small group with three peers. Practised turn-taking and topic "
              "maintenance in shared conversation.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=24)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    today = date.today()
    refs = [c.student_ref for c in store.open_cases()][: args.n] if not args.dry_run \
        else [f"stu_{i:04d}" for i in range(1, args.n + 1)]

    tally = {"clean": 0, "expired_licence": 0, "over_billed": 0,
             "under_billed": 0, "group_mismatch": 0}

    for i, ref in enumerate(refs):
        service, ptype, minutes, note_tmpl = rng.choice(SERVICES)
        iep = IEPService(
            goal_ref="G-3", service=service, minutes_per_session=minutes,
            sessions_per_week=2, provider_type=ptype,
            starts_on=today - timedelta(days=120),
            ends_on=today + timedelta(days=240))
        service_date = today - timedelta(days=rng.randint(1, 21))
        note = note_tmpl.format(p=rng.choice([60, 70, 75, 80]))
        licence = today + timedelta(days=400)
        units = minutes // 15

        roll = rng.random()
        if roll < 0.10:
            licence = service_date - timedelta(days=15); tally["expired_licence"] += 1
        elif roll < 0.18:
            units += 2; tally["over_billed"] += 1
        elif roll < 0.30:
            units -= 1; tally["under_billed"] += 1
        elif roll < 0.42:
            note = GROUP_NOTE; tally["group_mismatch"] += 1
        else:
            tally["clean"] += 1

        d = ServiceDelivery(
            student_ref=ref, goal_ref="G-3", service_date=service_date,
            minutes=minutes, units_billed=max(units, 0), note=note,
            provider_npi=f"1{rng.randint(100000000, 999999999)}",
            provider_type=ptype, provider_license_expires=licence)

        if not args.dry_run:
            from google.cloud import firestore
            db = firestore.Client(project=None)
            db.collection("deliveries").document(f"{ref}-{service_date}-G3").set(
                d.model_dump(mode="json") | {
                    "iep": iep.model_dump(mode="json"),
                    "medicaid_eligible": rng.random() < 0.88,
                    "assessed": False})

    verb = "would seed" if args.dry_run else "seeded"
    print(f"{verb} {len(refs)} sessions: " +
          ", ".join(f"{k}={v}" for k, v in tally.items()))


if __name__ == "__main__":
    main()
