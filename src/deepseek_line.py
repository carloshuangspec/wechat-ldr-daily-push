"""Generate one short English letter line with DeepSeek; never silently substitute text."""

from __future__ import annotations

import os
import sys

import requests

from daily_content import ENGLISH_LINE_MAX, DailyContentError, validate_inputs
from weather import UNAVAILABLE_CONFIG, UNAVAILABLE_REQUEST


ENDPOINT = "https://api.deepseek.com/chat/completions"
_DAYPARTS = frozenset({"morning", "afternoon", "evening", "night"})


class DeepSeekLineError(RuntimeError):
    """Fixed diagnostic, with no key, prompt or response text."""

    def __init__(self) -> None:
        super().__init__("DeepSeek line unavailable")


def daypart_from_hhmm(hhmm: str) -> str | None:
    """Map a local HH:MM clock string to a coarse daypart, or None if invalid."""
    if not isinstance(hhmm, str) or ":" not in hhmm:
        return None
    hour_text = hhmm.split(":", 1)[0]
    if not hour_text.isdigit():
        return None
    hour = int(hour_text)
    if not 0 <= hour <= 23:
        return None
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def sanitize_weather_fact(raw: str | None) -> str | None:
    """Keep only a short cityless ASCII weather phrase; drop offline/unavailable."""
    if not isinstance(raw, str):
        return None
    text = raw.replace("\u00b0", "").strip()
    if not text or text in {UNAVAILABLE_CONFIG, UNAVAILABLE_REQUEST}:
        return None
    if not text.isascii() or not text.isprintable() or len(text) > 24:
        return None
    return text


def build_love_line_prompt(
    theme: str | None = None,
    *,
    daypart_a: str | None = None,
    daypart_b: str | None = None,
    weather_a: str | None = None,
    weather_b: str | None = None,
) -> str:
    """Build the dual-reader generation prompt; never include secrets or city names."""
    prompt = (
        "Write ONE original English letter line for a couple who both receive the same message.\n"
        "\n"
        "Hard limits:\n"
        f"- Max {ENGLISH_LINE_MAX} printable ASCII characters "
        "(letters, digits, spaces, basic punctuation only).\n"
        "- No emojis, no non-ASCII.\n"
        "- Untitled: do not prefix with Note: or any other label.\n"
        "- Fresh each day; do not reuse a fixed phrase library or stock romance cliches.\n"
        "- Do not invent private memories, ordinary life events (coffee/commute), "
        "names, places, or either person's feelings.\n"
        "- You may only use provided facts: each side's local daypart and cityless weather phrases.\n"
        "- If a manual theme is provided, follow it within the hard limits; otherwise pick one tone: "
        "timezone handoff, no-pressure ping, weather/time detail, gentle humor, or (rarely) a tiny optional question.\n"
        "- A continuous shared-garden story vibe is OCCASIONAL only - not a daily check-in ritual.\n"
        "\n"
        "Timezone handoff must read well for BOTH recipients in one line "
        '(no single-sided "good morning" unless it still fits both).\n'
        "No-pressure lines must not demand a reply.\n"
        f"Questions, if any, must be skippable and still at most {ENGLISH_LINE_MAX} printable ASCII characters.\n"
        "Prefer plain, warm, slightly specific English over poetic melodrama.\n"
        "Output only the line, no quotes, emoji, explanations, or line breaks."
    )
    facts: list[str] = []
    if daypart_a in _DAYPARTS:
        facts.append(f"side_a_daypart={daypart_a}")
    if daypart_b in _DAYPARTS:
        facts.append(f"side_b_daypart={daypart_b}")
    if weather_a:
        facts.append(f"side_a_weather={weather_a}")
    if weather_b:
        facts.append(f"side_b_weather={weather_b}")
    if facts:
        prompt += "\nAllowed facts: " + "; ".join(facts) + "."
    if theme is not None:
        prompt += f" Today's optional theme: {theme}"
    return prompt


def _unavailable(reason: str) -> None:
    """Report one non-sensitive category, never a response or exception body."""
    print(f"line_failure={reason}", file=sys.stderr)
    raise DeepSeekLineError()


def _request_line(
    key: str, prompt: str, timeout: float | tuple[float, float]
) -> tuple[str | None, str | None]:
    """Return a validated line or one fixed failure class for this request."""
    data = None
    status = None
    try:
        response = requests.post(
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-flash",
                "messages": [{"role": "user", "content": prompt}],
                "thinking": {"type": "disabled"},
                "stream": False,
            },
            timeout=timeout,
            allow_redirects=False,
        )
        status = response.status_code
        if status == 200:
            data = response.json()
    except requests.RequestException:
        return None, "request_failed"
    except (ValueError, TypeError):
        return None, "invalid_json"

    if status != 200:
        safe_status = status if type(status) is int and status in {
            400, 401, 402, 403, 404, 408, 422, 429, 500, 503
        } else "other"
        return None, f"http_{safe_status}"
    if not isinstance(data, dict):
        return None, "invalid_response"
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        return None, "invalid_response"
    choice = choices[0]
    if not isinstance(choice, dict):
        return None, "invalid_response"
    if choice.get("finish_reason") != "stop":
        return None, "abnormal_finish"
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        return None, "invalid_response"
    line = message["content"].strip(" ")
    if (
        not 1 <= len(line) <= ENGLISH_LINE_MAX
        or not line.isascii()
        or not line.isprintable()
        or line[0] in "\"'"
        or line[-1] in "\"'"
    ):
        return None, "invalid_text"
    return line, None


def generate_love_line(
    theme: str | None = None,
    *,
    time_a: str | None = None,
    time_b: str | None = None,
    weather_a: str | None = None,
    weather_b: str | None = None,
    timeout: float | tuple[float, float] = (5, 30),
) -> str:
    """Ask for a fresh dual-reader letter line; reject any failed or partial completion."""
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        _unavailable("missing_key")

    if theme is not None:
        valid_theme = False
        try:
            validate_inputs("2026-01-01", theme, None)
            valid_theme = True
        except DailyContentError:
            pass
        if not valid_theme:
            _unavailable("invalid_theme")

    prompt = build_love_line_prompt(
        theme,
        daypart_a=daypart_from_hhmm(time_a) if time_a is not None else None,
        daypart_b=daypart_from_hhmm(time_b) if time_b is not None else None,
        weather_a=sanitize_weather_fact(weather_a),
        weather_b=sanitize_weather_fact(weather_b),
    )

    for attempt in range(3):
        line, failure = _request_line(key, prompt, timeout)
        if line is not None:
            print("line_source=deepseek", file=sys.stderr)
            return line
        if failure != "invalid_text" or attempt == 2:
            _unavailable(failure or "invalid_response")
    raise DeepSeekLineError()  # Unreachable; all three attempts ended above.
