"""Deterministic special-day facts for the daily push.

Pure functions: no keys, no network, no I/O. Day counts use the
same convention as dates.love_days: the start day itself counts
as day 1, so days = (today - start).days + 1.

The caller supplies the Together start date and the next meeting
date from the existing configuration (LOVE_START_DATE and
NEXT_MEET_DATE); this module does not hard-code those values.
Only the Known start date (2019-09-02) is fixed here, as given.
"""

from __future__ import annotations

from datetime import date, timedelta

KNOWN_START_DATE = date(2019, 9, 2)

# Qixi (the seventh day of the seventh lunar month), verified dates
# only. Do not guess other years: extend this table year by year
# from a reliable calendar source.
QIXI_BY_YEAR = {
    2027: date(2027, 8, 8),
}


def _days_since(start: date, today: date) -> int:
    """Day count with the start day counted as day 1."""
    return (today - start).days + 1


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    elif n % 10 == 1:
        suffix = "st"
    elif n % 10 == 2:
        suffix = "nd"
    elif n % 10 == 3:
        suffix = "rd"
    else:
        suffix = "th"
    return f"{n}{suffix}"


def _is_strictly_increasing_consecutive(n: int) -> bool:
    digits = str(n)
    return len(digits) >= 2 and all(
        int(digits[i + 1]) == int(digits[i]) + 1 for i in range(len(digits) - 1)
    )


def _is_repeated_digit(n: int) -> bool:
    digits = str(n)
    return len(digits) >= 3 and len(set(digits)) == 1


def _is_abab(n: int) -> bool:
    digits = str(n)
    return (
        len(digits) == 4
        and digits[0] == digits[2]
        and digits[1] == digits[3]
        and digits[0] != digits[1]
    )


def _numeric_facts(label: str, count: int) -> list:
    """Tier-3 number-aesthetic facts for one day count."""
    if count <= 0:
        return []
    facts = []
    if count >= 100 and count % 10 == 0:
        facts.append(f"today is day {count} {label}, a round number")
    if _is_strictly_increasing_consecutive(count):
        facts.append(f"today is day {count} {label}, whose digits rise one by one")
    if _is_repeated_digit(count):
        facts.append(f"today is day {count} {label}, with every digit the same")
    if _is_abab(count):
        facts.append(f"today is day {count} {label}, in an ABAB pattern")
    return facts


def get_special_day(today, together_start, next_meet=None, known_start=KNOWN_START_DATE):
    """Return (tier, fact) for a Shanghai date, or None.

    tier 1 is the highest tier. When several facts share the
    highest tier, they are joined into a single fact string.
    Lower-tier hits are dropped once a higher tier hits.
    When next_meet is None, the meeting-day rules are skipped.
    """
    tier1: list = []
    tier2: list = []
    tier3: list = []
    together_days = _days_since(together_start, today)
    known_days = _days_since(known_start, today)

    # Tier 1: meeting days.
    if next_meet is not None:
        if today == next_meet:
            tier1.append("today we meet in person")
        elif today + timedelta(days=1) == next_meet:
            tier1.append("tomorrow we meet in person")

    # Tier 1: monthly Together anniversary. Together started on
    # the 8th, so the 8th of each month is the monthly milestone.
    if today.day == 8 and today > together_start:
        months = (today.year - together_start.year) * 12 + (
            today.month - together_start.month
        )
        tier1.append(
            f"today marks {months} month{'s' if months != 1 else ''} together"
        )

    # Tier 1: Together anniversary (same month and day as the start).
    if (
        (today.month, today.day) == (together_start.month, together_start.day)
        and today.year > together_start.year
    ):
        years = today.year - together_start.year
        tier1.append(f"today is our {_ordinal(years)} anniversary together")

    # Tier 1: Known anniversary (same month and day as 2019-09-02).
    if (
        (today.month, today.day) == (known_start.month, known_start.day)
        and today.year > known_start.year
    ):
        years = today.year - known_start.year
        tier1.append(
            f"today is the {_ordinal(years)} anniversary "
            "of the day we first knew each other"
        )

    # Tier 1: birthdays and festival days.
    if (today.month, today.day) == (8, 26):
        tier1.append("today is Rachel's birthday")
    if (today.month, today.day) == (2, 14):
        tier1.append("today is Valentine's Day")
    if (today.month, today.day) == (5, 20):
        tier1.append("today is May 20, the 520 day for saying I love you")
    if (today.month, today.day) == (5, 21):
        tier1.append("today is May 21, the 521 day for saying I love you")
    if QIXI_BY_YEAR.get(today.year) == today:
        tier1.append("today is Qixi, the Chinese Valentine's Day")

    # Tier 2: round Together milestones and seasonal holidays.
    if together_days > 0 and (
        together_days % 100 == 0 or together_days % 50 == 0
    ):
        tier2.append(f"today is our {_ordinal(together_days)} day together")
    if (today.month, today.day) == (3, 14):
        tier2.append("today is White Day")
    if (today.month, today.day) == (12, 25):
        tier2.append("today is Christmas Day")
    if (today.month, today.day) == (1, 1):
        tier2.append("today is New Year's Day")

    # Tier 3: number aesthetics, checked for both day counts.
    tier3.extend(_numeric_facts("together", together_days))
    tier3.extend(
        _numeric_facts("since we first knew each other", known_days)
    )

    for tier, facts in ((1, tier1), (2, tier2), (3, tier3)):
        if facts:
            return tier, "; ".join(facts)
    return None


def get_special_fact(today, together_start, next_meet=None, known_start=KNOWN_START_DATE):
    """Return just the fact string for a date, or None."""
    result = get_special_day(today, together_start, next_meet, known_start)
    return result[1] if result is not None else None
