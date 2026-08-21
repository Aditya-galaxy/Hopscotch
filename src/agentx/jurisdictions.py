"""Statutory evaluation timelines, by jurisdiction.

IMPORTANT -- this table is ILLUSTRATIVE and is wired to synthetic cases only.
The federal 60-calendar-day baseline under IDEA is well established; the state
overrides below are simplified stand-ins chosen to exercise all three rule
types. Verify every entry against current state regulation before this touches
a real student record. The README says the same thing, deliberately.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class RuleType(str, Enum):
    CALENDAR_DAYS = "calendar_days"
    SCHOOL_DAYS = "school_days"
    BUSINESS_DAYS = "business_days"


@dataclass(frozen=True)
class Jurisdiction:
    key: str
    label: str
    rule: RuleType
    count: int
    # Some states pause the clock across long breaks but not short ones.
    exclude_breaks_longer_than: int | None = None


JURISDICTIONS: dict[str, Jurisdiction] = {
    "US_FEDERAL": Jurisdiction(
        "US_FEDERAL", "IDEA baseline -- 60 calendar days",
        RuleType.CALENDAR_DAYS, 60,
    ),
    "ST_ALPHA": Jurisdiction(
        "ST_ALPHA", "60 calendar days, pausing breaks over 5 school days",
        RuleType.CALENDAR_DAYS, 60, exclude_breaks_longer_than=5,
    ),
    "ST_BRAVO": Jurisdiction(
        "ST_BRAVO", "45 school days", RuleType.SCHOOL_DAYS, 45,
    ),
    "ST_CHARLIE": Jurisdiction(
        "ST_CHARLIE", "30 business days", RuleType.BUSINESS_DAYS, 30,
    ),
}


@dataclass(frozen=True)
class SchoolCalendar:
    """A district calendar. Non-instructional days pause a school-day clock."""
    district: str
    year_start: date
    year_end: date
    closures: frozenset[date]

    def is_school_day(self, d: date) -> bool:
        if d.weekday() >= 5:
            return False
        if d < self.year_start or d > self.year_end:
            return False
        return d not in self.closures


def demo_calendar() -> SchoolCalendar:
    """Synthetic 2026-27 calendar with a winter break long enough to matter."""
    closures = set()
    for day in range(21, 32):          # winter break, Dec 21-31
        closures.add(date(2026, 12, day))
    for day in range(1, 3):
        closures.add(date(2027, 1, day))
    closures.add(date(2026, 11, 26))   # single-day holiday -- deliberately short
    closures.add(date(2026, 11, 27))
    return SchoolCalendar(
        district="Demo Unified",
        year_start=date(2026, 8, 17),
        year_end=date(2027, 6, 11),
        closures=frozenset(closures),
    )
