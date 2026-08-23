"""Measure intake extraction against the corpus answer key.

Two numbers matter, and the second is the one people forget:

  accuracy    -- did it read the date correctly? A wrong date starts a legal
                 clock at the wrong moment.
  calibration -- when the signature is illegible, does confidence actually
                 drop? An extractor that is confidently wrong is worse than
                 one that is accurately unsure, because the whole downstream
                 design routes low confidence to a human.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from hopscotch.adk_runner import AgentRunFailed
from hopscotch.agents.intake import screened_extract

LOW_CONFIDENCE = 0.7


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="data/generated/corpus.jsonl")
    ap.add_argument("-n", type=int, default=0, help="limit, 0 = all")
    ap.add_argument("--no-screen", action="store_true", help="skip Model Armor")
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.corpus).read_text().splitlines() if l.strip()]
    if args.n:
        rows = rows[: args.n]

    n_illegible = n_illegible_lowconf = n_illegible_parsed = 0
    n_legible = n_legible_exact = n_legible_failed = 0
    blocked = failed = 0
    wrong: list[str] = []

    for i, row in enumerate(rows, 1):
        text = row["document_text"]
        is_illegible = "[illegible]" in text
        n_illegible += is_illegible
        n_legible += not is_illegible

        try:
            out = screened_extract(text, source=f"consent:{row['student_ref']}")
        except PermissionError as e:
            blocked += 1
            print(f"  {i:2}/{len(rows)} BLOCKED  {row['student_ref']}: {str(e)[:60]}")
            continue
        except AgentRunFailed as e:
            failed += 1
            n_legible_failed += not is_illegible
            print(f"  {i:2}/{len(rows)} FAILED   {row['student_ref']}: {str(e)[:70]}")
            continue

        truth = date.fromisoformat(row["truth"]["consent_signed_on"])
        hit = out.consent_signed_on == truth
        if is_illegible:
            n_illegible_parsed += 1
            # Correct behaviour is None or low confidence -- never a guess.
            if out.consent_signed_on is None or out.confidence < LOW_CONFIDENCE:
                n_illegible_lowconf += 1
            else:
                wrong.append(f"{row['student_ref']}: guessed {out.consent_signed_on} "
                             f"from an illegible date at conf={out.confidence}")
        elif hit:
            n_legible_exact += 1
        else:
            wrong.append(f"{row['student_ref']}: got {out.consent_signed_on}, want {truth}")
        flag = "ok " if hit else ("illegible" if is_illegible else "MISS")
        print(f"  {i:2}/{len(rows)} {flag:9} {row['student_ref']} conf={out.confidence:.2f}")

    attempted = n_legible - n_legible_failed
    pct = lambda a, b: f"  ({100*a/b:.0f}%)" if b else ""
    print("\n=== RESULTS ===")
    print(f"  documents            {len(rows)}")
    print(f"  legible              {n_legible}  (parsed {attempted})")
    print(f"  date exact           {n_legible_exact}/{attempted}"
          + pct(n_legible_exact, attempted))
    print(f"  illegible            {n_illegible}  (parsed {n_illegible_parsed})")
    print(f"  ...correctly unsure  {n_illegible_lowconf}/{n_illegible_parsed}"
          + pct(n_illegible_lowconf, n_illegible_parsed))
    print(f"  armor-blocked        {blocked}")
    print(f"  agent failures       {failed}")
    for w in wrong:
        print(f"  MISS {w}")


if __name__ == "__main__":
    main()
