"""Synthetic case corpus. No real student data touches this project, ever.

Deliberately ugly on purpose: intake-agent has to survive phone photos, OCR
noise, forwarded email chains, and a handwritten margin note, because that is
what actually lands in a district inbox.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

SCHOOLS = ["EL-004", "EL-011", "MS-002", "HS-001", "EL-019"]
JURISDICTIONS = ["US_FEDERAL", "ST_ALPHA", "ST_BRAVO", "ST_CHARLIE"]
REASONS = [
    "Teacher referral: reading fluency significantly below grade level",
    "Parent request following outside evaluation",
    "Child Find referral from preschool transition",
    "Repeat referral; prior evaluation declined by family in 2025",
]
NOISE = [
    "  Scanned by DISTRICT-MFP-3  page 1 of 2  ",
    "-----Original Message----- From: front.office@demo.k12 Sent: {d}",
    "[handwritten in margin: 'mom called again, wants update']",
    "l1ne n0ise fr0m 0CR -- c0nsent f0rm was ph0t0graphed at an angle",
]


def one(i: int, rng: random.Random) -> dict:
    signed = date(2026, 8, 1) + timedelta(days=rng.randint(0, 45))
    received = signed + timedelta(days=rng.randint(0, 9))
    body = [
        rng.choice(NOISE).format(d=received.isoformat()),
        f"PARENTAL CONSENT FOR INITIAL EVALUATION",
        f"Student ref: stu_{i:04d}",
        f"School: {rng.choice(SCHOOLS)}",
        f"Parent signature date: {signed.strftime('%m/%d/%Y')}",
        f"Received by district: {received.strftime('%m/%d/%Y')}",
        f"Reason: {rng.choice(REASONS)}",
    ]
    if rng.random() < 0.18:
        body[4] = "Parent signature date: [illegible]"   # forces low confidence
    if rng.random() < 0.12:
        body.append(rng.choice(NOISE).format(d=received.isoformat()))
    rng.shuffle(body[:1])
    return {
        "student_ref": f"stu_{i:04d}",
        "jurisdiction": rng.choice(JURISDICTIONS),
        "truth": {"consent_signed_on": signed.isoformat(),
                  "received_on": received.isoformat()},
        "document_text": "\n".join(body),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/generated/corpus.jsonl")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for i in range(1, args.n + 1):
            fh.write(json.dumps(one(i, rng)) + "\n")
    print(f"wrote {args.n} synthetic cases to {out}")
    print("`truth` is the extraction answer key -- use it to score intake-agent.")


if __name__ == "__main__":
    main()
