"""Generate one short English line with DeepSeek; never silently substitute text."""

from __future__ import annotations

import os
import sys

import requests

from daily_content import DailyContentError, validate_inputs
from daily_context import VALID_DAYPARTS, VALID_WEATHER_CUES


ENDPOINT = "https://api.deepseek.com/chat/completions"


class DeepSeekLineError(RuntimeError):
    """Fixed diagnostic, with no key, prompt or response text."""

    def __init__(self) -> None:
        super().__init__("DeepSeek line unavailable")


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
        not 1 <= len(line) <= 20
        or not line.isascii()
        or not line.isprintable()
        or line[0] in "\"'"
        or line[-1] in "\"'"
    ):
        return None, "invalid_text"
    return line, None


def generate_love_line(
    theme: str | None = None,
    timeout: float | tuple[float, float] = (5, 30),
    *,
    dayparts: tuple[str, str] | None = None,
    weather: tuple[str | None, str | None] | None = None,
) -> str:
    """Ask for a fresh line; reject any failed or partial completion."""
    if dayparts is not None and (
        type(dayparts) is not tuple
        or len(dayparts) != 2
        or any(type(part) is not str or part not in VALID_DAYPARTS for part in dayparts)
    ):
        _unavailable("invalid_context")
    if weather is not None and (
        type(weather) is not tuple
        or len(weather) != 2
        or any(
            cue is not None and (type(cue) is not str or cue not in VALID_WEATHER_CUES)
            for cue in weather
        )
    ):
        _unavailable("invalid_context")

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

    prompt = (
        "Write one original emotionally warm English line that both recipients receive "
        "in the same daily message. Make the same line feel right to either reader, "
        "not a greeting addressed to only one. Be affectionate and low-pressure; "
        "no reply demanded, guilt, or grand promises. Keep the English natural, "
        "not forced abbreviations or telegram-like shorthand. "
        "Use at most 20 printable ASCII characters including spaces. "
        "Output only the line, no quotes, emoji, or line breaks; no explanations. "
        "Do not invent memories, events, places, or feelings for the recipients."
    )
    if theme is not None:
        prompt += f" Today's optional theme: {theme}"
    else:
        prompt += (
            " Choose one naturally fitting angle, not a five-part checklist: "
            "a cross-time-zone handoff, a low-pressure thought, a real weather detail "
            "if supplied, gentle distance humor, or an occasional optional question "
            "that needs no reply. Mostly use gentle statements. Weather and time "
            "details must come only from the anonymous category cues below, if any; "
            "never guess more specific circumstances. Cues are optional to use."
        )
        if dayparts is not None:
            prompt += (
                f" Anonymous dayparts: first recipient: {dayparts[0]}; "
                f"second recipient: {dayparts[1]}."
            )
        if weather is not None:
            known_weather = [
                f"{reader} recipient: {cue}"
                for reader, cue in zip(("first", "second"), weather)
                if cue is not None
            ]
            if known_weather:
                prompt += f" Anonymous weather cues: {'; '.join(known_weather)}."

    for attempt in range(3):
        line, failure = _request_line(key, prompt, timeout)
        if line is not None:
            print("line_source=deepseek", file=sys.stderr)
            return line
        if failure != "invalid_text" or attempt == 2:
            _unavailable(failure or "invalid_response")
    raise DeepSeekLineError()  # Unreachable; all three attempts ended above.
