"""Generate one short English letter line with DeepSeek; never silently substitute text."""

from __future__ import annotations

import os
import re
import sys

import requests

from daily_content import (
    ENGLISH_LINE_MAX,
    DailyContentError,
    contains_forbidden_note_label,
    validate_inputs,
)
from weather import UNAVAILABLE_CONFIG, UNAVAILABLE_REQUEST

ENDPOINT = "https://api.deepseek.com/chat/completions"
_DAYPARTS = frozenset({"morning", "afternoon", "evening", "night"})
# Generation attempts for content-only rejections (invalid_text/forbidden_label).
# HTTP, auth, network and malformed-response failures still stop immediately.
MAX_ATTEMPTS = 5
# Ask for well under the hard cap so a slightly long reply still fits.
TARGET_LINE_LEN = 40
# Safety cap for generated text, not a creative target. Ordinary days
# still aim for TARGET_LINE_LEN and one line; special days may use
# up to this cap and at most GENERATED_MAX_LINES lines.
GENERATED_LINE_MAX = 200
GENERATED_MAX_LINES = 4
# Deterministic, meaning-preserving character mappings for generated text only.
_CURLY_SINGLE = "\u2018\u2019\u201a\u201b"
_CURLY_DOUBLE = "\u201c\u201d\u201e\u201f"
_DASHES = "\u2013\u2014"
_QUOTE_MAP = str.maketrans(
    {**{c: "'" for c in _CURLY_SINGLE}, **{c: '"' for c in _CURLY_DOUBLE}}
)
_DASH_MAP = str.maketrans({c: "-" for c in _DASHES})
_WRAPPERS = "\"'`"
# Horizontal whitespace only; line breaks are never collapsed (they stay multiline).
_INLINE_SPACE_RE = re.compile(r"[^\S\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]+")
_LINE_BREAKS = frozenset("\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")
# Fixed diagnostic reason tokens for invalid_text; never include line text.
INVALID_TEXT_REASONS = frozenset({
    "empty",
    "multiline",
    "non_ascii",
    "non_printable",
    "too_long",
    "quoted",
    "markdown",
    "no_end_punct",
    "ellipsis",
})


class DeepSeekLineError(RuntimeError):
    """Fixed diagnostic, with no key, prompt or response text."""

    def __init__(self) -> None:
        super().__init__("DeepSeek line unavailable")


def daypart_from_hhmm(hhmm: str) -> str | None:
    """Map a local HH:MM clock string to a coarse daypart, or None if invalid."""
    if not isinstance(hhmm, str) or ":" not in hhmm:
        return None
    hour_text, _, minute_text = hhmm.partition(":")
    try:
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    total = hour * 60 + minute
    if total < 5 * 60:
        return "night"
    if total < 12 * 60:
        return "morning"
    if total < 18 * 60:
        return "afternoon"
    return "evening"


def _require_time_and_weather(*values: object) -> None:
    # A missing clock or weather value means the shared line cannot be
    # honestly built, so fail closed instead of substituting a guess.
    for value in values:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise DeepSeekLineError


def _normalize_generated_line(text: str) -> str:
    # Never invent a period, word or replacement line. Only map curly
    # quotes and dashes to ASCII, and trim whitespace and wrappers.
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.translate(_QUOTE_MAP).translate(_DASH_MAP)
    text = _INLINE_SPACE_RE.sub(" ", text)
    lines = text.split("\n")
    lines = [line.strip() for line in lines]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    text = "\n".join(lines)
    text = text.strip(" ")
    text = text.strip(_WRAPPERS)
    if not text:
        return ""
    if text[-1] in ".,!?":
        return text
    stripped = text.rstrip(" ")
    while stripped and stripped[-1] in ".,!?":
        stripped = stripped[:-1]
    if stripped:
        return stripped
    return ""


def _validate_daily_inputs(theme, time_a, time_b, weather_a, weather_b):
    # Theme-free daily lines still need the same structural validation
    # as a manually supplied exact line, so the card is never truncated.
    validate_inputs(
        theme=theme,
        time_a=time_a,
        time_b=time_b,
        weather_a=weather_a,
        weather_b=weather_b,
    )
    _require_time_and_weather(time_a, time_b, weather_a, weather_b)


def invalid_text_reason(text: str) -> str | None:
    """Classify a candidate line without ever logging its text."""
    if not text:
        return "empty"
    if any(ch in _LINE_BREAKS and ch != "\n" for ch in text):
        return "multiline"
    if text.count("\n") >= GENERATED_MAX_LINES:
        return "multiline"
    if not text.isascii():
        return "non_ascii"
    if any(not ch.isprintable() and ch not in _LINE_BREAKS for ch in text):
        return "non_printable"
    if len(text) > GENERATED_LINE_MAX:
        return "too_long"
    if text[0] in "\"'" or text[-1] in "\"'":
        return "quoted"
    if "`" in text or "*" in text or "#" in text:
        return "markdown"
    if text[-1] not in ".!?":
        return "no_end_punct"
    if "\u2026" in text or "..." in text:
        return "ellipsis"
    if contains_forbidden_note_label(text):
        return "forbidden_label"
    return None


def _request_once(
    api_key: str, prompt: str
) -> tuple[str | None, str | None, int | None]:
    # Returns (normalized_line, diagnostic_reason, http_status).
    # Content-only reasons are retryable; HTTP failures stop immediately.
    try:
        response = requests.post(
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 120,
            },
            timeout=30,
        )
    except requests.RequestException:
        return None, "http_error", None
    if response.status_code != 200:
        return None, "http_error", response.status_code
    try:
        payload = response.json()
    except ValueError:
        return None, "malformed_response", response.status_code
    if not isinstance(payload, dict):
        return None, "malformed_response", response.status_code
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, "malformed_response", response.status_code
    first = choices[0]
    if not isinstance(first, dict):
        return None, "malformed_response", response.status_code
    message = first.get("message")
    if not isinstance(message, dict):
        return None, "malformed_response", response.status_code
    content = message.get("content")
    if not isinstance(content, str):
        return None, "malformed_response", response.status_code
    normalized = _normalize_generated_line(content)
    reason = invalid_text_reason(normalized)
    if reason is not None:
        return None, reason, response.status_code
    return normalized, None, response.status_code


def _request_with_retries(api_key: str, prompt: str) -> str:
    # Retry only when the model returned a well-formed but unusable
    # line (for example, too long or missing end punctuation).
    seen_reasons: set[str] = set()
    for _ in range(MAX_ATTEMPTS):
        line, reason, _status = _request_once(api_key, prompt)
        if line is not None:
            return line
        if reason in ("http_error", "malformed_response"):
            raise DeepSeekLineError
        if reason is None:
            raise DeepSeekLineError
        if reason in seen_reasons:
            raise DeepSeekLineError
        seen_reasons.add(reason)
    raise DeepSeekLineError


def build_love_line_prompt(
    theme=None,
    *,
    daypart_a,
    daypart_b,
    weather_a,
    weather_b,
    special_fact=None,
):
    if theme is not None and (
        not isinstance(theme, str)
        or not theme.strip()
        or "\n" in theme
        or len(theme) > 120
    ):
        raise DeepSeekLineError
    if special_fact is not None and (
        not isinstance(special_fact, str)
        or not special_fact.strip()
        or any(ch in _LINE_BREAKS for ch in special_fact)
    ):
        raise DeepSeekLineError
    if daypart_a is not None and daypart_a not in _DAYPARTS:
        raise DeepSeekLineError
    if daypart_b is not None and daypart_b not in _DAYPARTS:
        raise DeepSeekLineError
    time_a = daypart_a or "this part of the day"
    time_b = daypart_b or "this part of the day"
    weather_a_text = weather_a or "unknown"
    weather_b_text = weather_b or "unknown"
    if weather_a == UNAVAILABLE_REQUEST or weather_b == UNAVAILABLE_REQUEST:
        weather_note = "One or both weather feeds failed, so do not mention the weather."
    elif weather_a is None or weather_b is None:
        weather_note = "No weather information is available today, so do not mention the weather."
    else:
        weather_note = f"Weather today: {weather_a_text} in one city, {weather_b_text} in the other."
    prompt = (
        "Write one original English love line for a long-distance couple, for both recipients to read together.\n"
        "- Exactly one line: no line breaks.\n"
        "- One complete sentence only, with exactly one verb of motion or travel.\n"
        f"- Max {ENGLISH_LINE_MAX} printable ASCII characters in total, counting spaces and punctuation.\n"
        "- Do not write a long sentence or a multi-line poem: aim for 40 characters or fewer.\n"
        "- No ellipsis characters, including \"...\".\n"
        "- No \"Note:\" labels or explanations.\n"
        "- No markdown, no quotation marks, no curly quotes, no em dashes.\n"
        "- Do not repeat or copy a previous line.\n"
        "- Do not use the exact phrase \"an endless road\".\n"
        "- Do not mention love or missing someone directly. Show it through a single image or action.\n"
        "- Do not use the weather as the main image.\n"
        "- One style trial: in the manner of Borges, about time, the moon, mirrors, labyrinths, dreams, or an endless road; never quote Borges, never name him, and never copy a line from his poems or stories.\n"
        f"- Today is {time_a} in one city and {time_b} in the other.\n"
        f"- {weather_note}\n"
        f"- Theme for today: {theme}." if theme else "- No theme today."
        "\nReturn only the line."
    )
    if special_fact is not None:
        prompt = prompt.replace(
            "Exactly one line: no line breaks.",
            "For this special day, write a short poem of 2-4 lines, or one longer sentence.",
        )
        prompt = prompt.replace(
            f"Max {ENGLISH_LINE_MAX} printable ASCII characters in total, counting spaces and punctuation.",
            f"Max {GENERATED_LINE_MAX} printable ASCII characters in total, counting spaces and punctuation, and at most {GENERATED_MAX_LINES} lines.",
        )
        prompt = prompt.replace(
            "Do not write a long sentence or a multi-line poem: aim for 40 characters or fewer.",
            "A short poem of 2-4 lines, or one longer sentence, is welcome today.",
        )
        special_line = (
            f"Today is a special day: {special_fact}. "
            "This line must be written about this day."
        )
        if "Return only the line." in prompt:
            prompt = prompt.replace(
                "Return only the line.", f"{special_line}\nReturn only the line."
            )
        else:
            prompt += f"\n{special_line}\nReturn only the line."
    return prompt


def generate_love_line(
    theme=None,
    *,
    time_a,
    time_b,
    weather_a,
    weather_b,
    special_fact=None,
):
    _validate_daily_inputs(theme, time_a, time_b, weather_a, weather_b)
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise DeepSeekLineError
    prompt = build_love_line_prompt(
        theme,
        daypart_a=daypart_from_hhmm(time_a),
        daypart_b=daypart_from_hhmm(time_b),
        weather_a=weather_a,
        weather_b=weather_b,
        special_fact=special_fact,
    )
    try:
        return _request_with_retries(api_key, prompt)
    except DeepSeekLineError:
        raise
    except Exception:
        raise DeepSeekLineError


if __name__ == "__main__":
    sys.exit("deepseek_line is a library module; run src/main.py instead")
