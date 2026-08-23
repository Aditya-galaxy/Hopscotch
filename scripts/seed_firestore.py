"""Seed synthetic cases so the unattended clock has real work to do.

Consent dates are spread deliberately rather than uniformly. A corpus where
every deadline lands two months out produces nine days of "scanned: 42,
escalated: 0" -- technically unattended operation, and evidence of nothing.
Spreading them means escalations fire across the whole window, so the trace
history shows the fleet actually deciding things.

All data is synthetic. No real student record is involved.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from hopscotch import store
from hopscotch.deadlines import recompute
from hopscotch.schemas import Case, CaseStage, ConsentEvent

# days-until-deadline band -> share of the corpus
BANDS = [((-3, 1), 0.10),    # already overdue or due today: the loud cases
         ((2, 8), 0.20),     # inside T-7: escalations fire this week
         ((9, 20), 0.25),    # will cross T-14 during the demo window
         ((21, 55), 0.45)]   # quiet background load


def target_days(rng: random.Random) -> int:
    r, roll = rng.random(), 0.0
    for (lo, hi), share in BANDS:
        roll += share
        if r <= roll:
            return rng.randint(lo, hi)
    return rng.randint(21, 55)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="data/generated/corpus.jsonl")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    today = date.today()
    rows = [json.loads(l) for l in Path(args.corpus).read_text().splitlines() if l.strip()]

    written = 0
    for row in rows:
        want = target_days(rng)
        # Walk backwards from the desired days-remaining to a consent date that
        # produces it under this case's own jurisdiction rules.
        signed = today - timedelta(days=60 - want)
        case = Case(
            student_ref=row["student_ref"],
            school_code=rng.choice(["EL-004", "EL-011", "MS-002", "HS-001", "EL-019"]),
            jurisdiction=row["jurisdiction"],
            stage=CaseStage.CONSENT_RECEIVED,
            consent=ConsentEvent(
                student_ref=row["student_ref"],
                school_code="EL-004",
                jurisdiction=row["jurisdiction"],
                consent_signed_on=signed,
                received_on=signed + timedelta(days=rng.randint(0, 4)),
                referral_reason=row.get("document_text", "")[:120],
                confidence=round(rng.uniform(0.72, 0.99), 2),
                source_document=f"{row['student_ref']}-consent.pdf",
            ),
        )
        comp = recompute(case, today=today)
        case.deadline = comp
        if args.dry_run:
            print(f"  {case.student_ref}  {case.jurisdiction:11} due {comp.due_on} "
                  f"({comp.days_remaining:+d}d)")
        else:
            store.upsert_case(case)
        written += 1

    print(f"{'would seed' if args.dry_run else 'seeded'} {written} synthetic cases")


if __name__ == "__main__":
    main()
