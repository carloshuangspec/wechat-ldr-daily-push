"""Validate a dated manual line or theme before selecting today's content."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date


class DailyContentError(ValueError):
    """A fixed, safe error that never includes the supplied configuration."""

    def __init__(self) -> None:
        super().__init__("Invalid daily content configuration.")


# English letter body alone. love_line = body + "\nKnown: ≈N days" must stay ≤64 (wechat.py).
ENGLISH_LINE_MAX = 42
LOVE_LINE_MAX = 64

_DAY_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_FIELDS = frozenset({"date", "theme", "exact"})


def validate_inputs(day: str, theme: str | None, exact: str | None) -> dict[str, str]:
    """Return canonical editor fields, omitting absent optional values."""
    if not isinstance(day, str) or not _DAY_RE.fullmatch(day):
        raise DailyContentError()
    try:
        parsed_day = date.fromisoformat(day)
    except ValueError:
        parsed_day = None
    if parsed_day is None or parsed_day.isoformat() != day:
        raise DailyContentError()

    result = {"date": day}
    if theme is not None and theme != "":
        if (
            not isinstance(theme, str)
            or not 1 <= len(theme) <= 120
            or not theme.strip()
            or any(
                unicodedata.category(char).startswith("C")
                or unicodedata.category(char) in {"Zl", "Zp"}
                for char in theme
            )
        ):
            raise DailyContentError()
        result["theme"] = theme

    if exact is not None and exact != "":
        if (
            not isinstance(exact, str)
            or not 1 <= len(exact) <= ENGLISH_LINE_MAX
            or not exact.strip()
            or any(not 32 <= ord(char) <= 126 for char in exact)
        ):
            raise DailyContentError()
        result["exact"] = exact

    if len(result) == 1:
        raise DailyContentError()
    return result


def _validate_config(config: object) -> dict[str, str]:
    if (
        not isinstance(config, dict)
        or "date" not in config
        or not config.keys() <= _FIELDS
        or any(config.get(field) in (None, "") for field in ("theme", "exact") if field in config)
    ):
        raise DailyContentError()
    return validate_inputs(config["date"], config.get("theme"), config.get("exact"))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DailyContentError()
        result[key] = value
    return result


def parse_config(raw: str | None) -> dict[str, str] | None:
    """Parse strict JSON config; missing/blank config means no manual content."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if not isinstance(raw, str):
        raise DailyContentError()
    try:
        config = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, TypeError, RecursionError):
        config = None
    # Raise only after leaving the handler: an exception context can retain raw JSON.
    return _validate_config(config)


def choose_line(
    config: dict[str, str] | None, shanghai_day: date
) -> tuple[str | None, str | None, str, str]:
    """Choose manual exact text, a generation theme, or the default path."""
    if config is None:
        return None, None, "generated", "none"
    validated = _validate_config(config)  # Even stale content must be valid.
    if validated["date"] != shanghai_day.isoformat():
        return None, None, "generated", "stale"
    if "exact" in validated:
        return validated["exact"], None, "manual", "active"
    return None, validated["theme"], "generated", "active"
