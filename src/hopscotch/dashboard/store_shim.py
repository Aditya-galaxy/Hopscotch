"""Reads the tour needs that the main store does not expose per-case.

Kept separate rather than widened into store.py the day before a freeze: the
dashboard is the only caller, and a narrow read used by one screen does not
need to become part of the storage interface every other module sees.
"""
from __future__ import annotations


def readiness_rows(limit: int = 500) -> list[dict]:
    """Every claim-readiness assessment, newest first where a date exists."""
    from ..store import _client

    rows = [d.to_dict() for d in
            _client().collection("claim_readiness").limit(limit).stream()]
    return sorted(rows, key=lambda r: str(r.get("assessed_at", "")), reverse=True)
