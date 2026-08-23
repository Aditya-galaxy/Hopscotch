"""Scan a skill folder and print the verdict.

    python -m hopscotch.skills.cli data/replicas/credential-helper --origin community
    python -m hopscotch.skills.cli data/corpora/mattpocock-skills --all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .gate import review
from .model import Decision, Origin
from .parse import parse_skill
from .reviewers import StructuralReviewer

MARK = {Decision.APPROVE: "APPROVE ", Decision.QUARANTINE: "QUARANTINE",
        Decision.REJECT: "REJECT  "}


def scan_one(path: Path, origin: Origin, structural_only: bool) -> Decision:
    pkg = parse_skill(path, origin=origin)
    report = review(
        pkg,
        reviewers=[StructuralReviewer()] if structural_only else None,
        require_all=not structural_only,
    )
    print(f"{MARK[report.decision]}  {report.skill_name:<32} {report.content_hash[:12]}")
    print(f"            {report.reasoning}")
    for f in report.findings:
        print(f"            - [{f.severity.value}] {f.category.value}: {f.summary}")
    for r in report.results:
        if not r.ok:
            print(f"            ! {r.reviewer}: {r.note}")
    print()
    return report.decision


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--origin", default="community",
                    choices=[o.value for o in Origin])
    ap.add_argument("--all", action="store_true", help="scan every skill beneath path")
    ap.add_argument("--structural-only", action="store_true",
                    help="skip reviewers that need a model call")
    args = ap.parse_args()

    origin = Origin(args.origin)
    targets = ([m.parent for m in sorted(args.path.rglob("SKILL.md"))]
               if args.all else [args.path])
    if not targets:
        print(f"no SKILL.md under {args.path}", file=sys.stderr)
        return 2

    tally: dict[Decision, int] = {}
    for t in targets:
        d = scan_one(t, origin, args.structural_only)
        tally[d] = tally.get(d, 0) + 1

    print("  ".join(f"{k.value}={v}" for k, v in sorted(tally.items(), key=lambda x: x[0].value)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
