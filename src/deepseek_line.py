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
        "Write ONE original, romantic English sentence from me to my girlfriend; "
        "both receive the same message.\n"
        "\n"
        "Hard limits:\n"
        f"- Max {ENGLISH_LINE_MAX} printable ASCII characters, counting spaces and punctuation; "
        f"aim for {TARGET_LINE_LEN} characters or fewer (about 6 to 9 words). Short beats clever.\n"
        "- Plain printable ASCII only: letters, digits, spaces, and . , ! ? ' - only.\n"
        "- Use the plain ASCII apostrophe ' only; no curly quotes, no em or en dashes, "
        "no ellipsis, no emojis, no non-ASCII.\n"
        "- Untitled: do not prefix with Note: or any other label; never write the word Note followed by a colon.\n"
        "- No quotation marks or backticks around the line, no markdown (no *, _, #, >), "
        "no lists, no explanations.\n"
        "- Exactly one line: no line breaks.\n"
        "- A complete sentence directly expressing tender love, longing, or choosing her. "
        "Address her as you; end with a period, !, or ?. Never use an ellipsis or an unfinished thought.\n"
        "- Fresh each day; do not reuse a fixed phrase library or stock romance cliches.\n"
        "- Do not invent private memories, ordinary life events (coffee/commute), "
        "names, places, or the girlfriend's feelings. The speaker may express his own affection.\n"
        "- The only situational facts you may use are each side's local daypart and cityless weather phrases.\n"
        "- If a manual theme is provided, follow it within the hard limits; otherwise pick one tone: "
        "timezone handoff, no-pressure ping, weather/time detail, gentle humor, or (rarely) a tiny optional question.\n"
        "- Whatever the tone, make her feel loved; weather/time is only background, not the point.\n"
        "- A continuous shared-garden story vibe is OCCASIONAL only - not a daily check-in ritual.\n"
        "\n"
        "Timezone handoff must read well for BOTH recipients in one line "
        '(no single-sided "good morning" unless it still fits both).\n'
        "No-pressure lines must not demand a reply.\n"
        f"Questions, if any, must be skippable and still at most {ENGLISH_LINE_MAX} printable ASCII characters.\n"
        "Prefer plain, warm, slightly specific English over poetic melodrama.\n"
        "Output only the single line itself, ending with . or ! or ?, "
        "with no quotes, markdown, labels, emoji, explanations, or line breaks."
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
) -> tuple[str | None, str | None, tuple[str, ...]]:
    """Return a validated line (plus normalization tokens) or one fixed failure class."""
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
        return None, "request_failed", ()
    except (ValueError, TypeError):
        return None, "invalid_json", ()

    if status != 200:
        safe_status = status if type(status) is int and status in {
            400, 401, 402, 403, 404, 408, 422, 429, 500, 503
        } else "other"
        return None, f"http_{safe_status}", ()
    if not isinstance(data, dict):
        return None, "invalid_response", ()
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        return None, "invalid_response", ()
    choice = choices[0]
    if not isinstance(choice, dict):
        return None, "invalid_response", ()
    if choice.get("finish_reason") != "stop":
        return None, "abnormal_finish", ()
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        return None, "invalid_response", ()
    line, applied = normalize_generated_line(message["content"])
    reason = invalid_text_reason(line)
    if reason is not None:
        return None, f"invalid_text:{reason}", ()
    return line, None, applied


def normalize_generated_line(text: str) -> tuple[str, tuple[str, ...]]:
    """Apply only deterministic, meaning-preserving cleanups to model output.

    Never truncates, never rewrites words, never strips or rewrites Note:.
    Returns the normalized text and fixed tokens naming which steps changed it.
    """
    applied: list[str] = []
    out = text.strip()
    if out != text:
        applied.append("outer_space")
    step = out.translate(_QUOTE_MAP)
    if step != out:
        applied.append("curly_quotes")
    out = step
    step = out.translate(_DASH_MAP)
    if step != out:
        applied.append("dashes")
    out = step
    if len(out) >= 2 and out[0] in _WRAPPERS and out[-1] == out[0]:
        out = out[1:-1].strip()
        applied.append("wrapping_quotes")
    step = _INLINE_SPACE_RE.sub(" ", out)
    if step != out:
        applied.append("inner_space")
    out = step
    return out, tuple(applied)


def invalid_text_reason(line: str) -> str | None:
    """Return a fixed reason token for a rejected line, forbidden_label, or None if valid."""
    if not line:
        return "empty"
    if any(char in _LINE_BREAKS for char in line):
        return "multiline"
    if not line.isascii():
        return "non_ascii"
    if not line.isprintable():
        return "non_printable"
    if len(line) > ENGLISH_LINE_MAX:
        return "too_long"
    if line[0] in _WRAPPERS or line[-1] in _WRAPPERS:
        return "quoted"
    if contains_forbidden_note_label(line):
        return "forbidden_label"
    if "..." in line:
        return "ellipsis"
    if line[-1] not in ".!?":
        if line[-1] in "*_" or line[0] in "*_#>":
            return "markdown"
        return "no_end_punct"
    return None


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

    last_failure = "invalid_response"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        line, failure, applied = _request_line(key, prompt, timeout)
        if line is not None:
            if applied:
                # Fixed step names only, never the text before or after.
                print(f"line_normalized={','.join(applied)}", file=sys.stderr)
            print("line_source=deepseek", file=sys.stderr)
            return line
        last_failure = failure or "invalid_response"
        if not last_failure.startswith("invalid_text:"):
            _unavailable(last_failure)
        reason = last_failure.split(":", 1)[1]
        category = "forbidden_label" if reason == "forbidden_label" else "invalid_text"
        if attempt < MAX_ATTEMPTS:
            # Fixed tokens only: attempt number, category, reason. Never the text.
            if category == "invalid_text":
                print(f"line_retry={attempt} category=invalid_text reason={reason}", file=sys.stderr)
            else:
                print(f"line_retry={attempt} category=forbidden_label", file=sys.stderr)
    reason = last_failure.split(":", 1)[1]
    if reason == "forbidden_label":
        _unavailable("forbidden_label")
    _unavailable(f"invalid_text reason={reason}")
    raise DeepSeekLineError()  # Unreachable; _unavailable always raises.
