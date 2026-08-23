"""Publish every agent card in registry/ to the Agent Registry."""
from __future__ import annotations

import argparse

from hopscotch.registry import discover, load_cards, publish


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cards = load_cards()
    for c in cards:
        line = (f"  {c.name:18} v{c.version:8} {c.department:24} "
                f"{len(c.scopes)} scopes")
        if args.dry_run:
            print(line + "  (dry run)")
        else:
            print(line + "  -> " + publish(c))

    if not args.dry_run:
        print(f"\npublished {len(cards)} agents")
        print("\ndiscovery, as another department would see it:")
        for r in discover(scope="case.read_dates"):
            print(f"  {r['name']} v{r['version']} — {r['department']}")


if __name__ == "__main__":
    main()
