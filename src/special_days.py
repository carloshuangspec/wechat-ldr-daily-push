"""Deterministic special-day facts for the daily love line.

Pure functions only: no secrets, no network, no side effects. Day counts
use the same convention as dates.love_days (the start day counts as day 1).
"""

from datetime import date, timedelta

KNOWN_START_DATE = date(2019, 9, 2)

# Verified Qixi (lunar July 7) dates only. Extend year by year from a reliable
# calendar source; do not guess unlisted years.
QIXI_BY_YEAR = {2027: date(2027, 8, 8)}


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


def _is_round_number(n: int) -> bool:
    return n >= 100 and n % 10 == 0


def _is_increasing_digits(n: int) -> bool:
    digits = str(n)
    return len(digits) >= 3 and all(
        int(digits[i]) + 1 == int(digits[i + 1]) for i in range(len(digits) - 1)
    )


def _is_repeated_digits(n: int) -> bool:
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


def _numeric_facts(days: int, label: str) -> list[str]:
    facts = []
    if _is_round_number(days):
        facts.append(f"today is day {days} {label}, a round number")
    if _is_increasing_digits(days):
        facts.append(f"today is day {days} {label}, a rising number")
    if _is_repeated_digits(days):
        facts.append(f"today is day {days} {label}, a repeated-digit number")
    if _is_abab(days):
        facts.append(f"today is day {days} {label}, an ABAB number")
    return facts


def _tier1_facts(
    today: date, together_start: date, next_meet: date | None
) -> list[str]:
    facts = []
    if next_meet is not None:
        if today == next_meet:
            facts.append("today we meet")
        elif today == next_meet - timedelta(days=1):
            facts.append("tomorrow we meet")
    months = (today.year - together_start.year) * 12 + (
        today.month - together_start.month
    )
    if today.day == 8 and months >= 1 and today > together_start:
        facts.append(
            f"today marks {months} month{'s' if months != 1 else ''} together"
        )
    # One-off: 2026-11-08 is a Borges-style love confession day.
    if today == date(2026, 11, 8):
        facts.append("the poem should be a Borges-style love confession")
    if today.month == 7 and today.day == 8 and today > together_start:
        years = today.year - together_start.year
        if years >= 1:
            facts.append(
                f"today is our {years}-year together anniversary"
                if years == 1
                else f"today is our {years}th together anniversary"
            )
    if today.month == 9 and today.day == 2:
        facts.append("today is our known anniversary")
    if today.month == 8 and today.day == 26:
        facts.append("today is Rachel's birthday")
    if today.month == 2 and today.day == 14:
        facts.append("today is Valentine's Day")
    if today.month == 5 and today.day == 20:
        facts.append("today is 520 day")
    if today.month == 5 and today.day == 21:
        facts.append("today is 521 day")
    if QIXI_BY_YEAR.get(today.year) == today:
        facts.append("today is Qixi Festival")
    return facts


def _tier2_facts(today: date, together_days: int) -> list[str]:
    facts = []
    if together_days % 100 == 0 or together_days % 50 == 0:
        facts.append(f"today is the {_ordinal(together_days)} day together")
    if today.month == 3 and today.day == 14:
        facts.append("today is White Day")
    if today.month == 12 and today.day == 25:
        facts.append("today is Christmas Day")
    if today.month == 1 and today.day == 1:
        facts.append("today is New Year's Day")
    return facts


def _tier3_facts(today: date, together_days: int, known_days: int) -> list[str]:
    facts = _numeric_facts(together_days, "together")
    if today.month == 1 and today.day == 1:
        facts.append("today is New Year's Day")
    if today.month == 2 and today.day == 14:
        facts.append("today is Valentine's Day")
    if today.month == 8 and today.day == 17:
        facts.append("today is Shuqi's birthday")
    return facts + _numeric_facts(known_days, "known")


def get_special_day(
    today: date,
    together_start: date,
    next_meet: date | None = None,
    known_start: date = KNOWN_START_DATE,
) -> tuple[int, str] | None:
    """Return (tier, fact) for a special day, or None for an ordinary day."""
    together_days = (today - together_start).days + 1
    known_days = (today - known_start).days + 1
    tier1 = _tier1_facts(today, together_start, next_meet)
    if tier1:
        return 1, "; ".join(tier1)
    tier2 = _tier2_facts(today, together_days)
    if tier2:
        return 2, "; ".join(tier2)
    tier3 = _tier3_facts(today, together_days, known_days)
    if tier3:
        return 3, "; ".join(tier3)
    return None
