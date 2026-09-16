"""Generate one short English line with DeepSeek; never silently substitute text."""

from __future__ import annotations

import os
import sys

import requests

from daily_content import DailyContentError, validate_inputs


ENDPOINT = "https://api.deepseek.com/chat/completions"


class DeepSeekLineError(RuntimeError):
    """Fixed diagnostic, with no key, prompt or response text."""

    def __init__(self) -> None:
        super().__init__("DeepSeek line unavailable")


def _unavailable(reason: str) -> None:
    """Report one non-sensitive category, never a response or exception body."""
    print(f"line_failure={reason}", file=sys.stderr)
    raise DeepSeekLineError()


def generate_love_line(
    theme: str | None = None, timeout: float | tuple[float, float] = (5, 30)
) -> str:
    """Ask for a fresh line; reject any failed or partial completion."""
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
        "Write one warm, natural English line for my long-distance partner. "
        "We each have our own lives and care about ordinary moments. "
        "Use at most 20 printable ASCII characters including spaces. "
        "Output only the line, no quotes, emoji, explanations, or line breaks. "
        "Do not invent today's events or the other person's thoughts."
    )
    if theme is not None:
        prompt += f" Today's optional theme: {theme}"

    data = None
    status = None
    failure = None
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
        failure = "request_failed"
    except (ValueError, TypeError):
        failure = "invalid_json"

    if failure is not None:
        _unavailable(failure)
    if status != 200:
        safe_status = status if type(status) is int and status in {
            400, 401, 402, 403, 404, 408, 422, 429, 500, 503
        } else "other"
        _unavailable(f"http_{safe_status}")
    if not isinstance(data, dict):
        _unavailable("invalid_response")
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        _unavailable("invalid_response")
    choice = choices[0]
    if not isinstance(choice, dict):
        _unavailable("invalid_response")
    if choice.get("finish_reason") != "stop":
        _unavailable("abnormal_finish")
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        _unavailable("invalid_response")
    line = message["content"].strip(" ")
    if (
        not 1 <= len(line) <= 20
        or not line.isascii()
        or not line.isprintable()
        or line[0] in "\"'"
        or line[-1] in "\"'"
    ):
        _unavailable("invalid_text")
    print("line_source=deepseek", file=sys.stderr)
    return line
