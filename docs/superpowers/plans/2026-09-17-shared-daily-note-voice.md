# Shared Daily Note Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the existing DeepSeek-generated shared English line a varied, grounded, low-pressure voice without a fixed line rotation or extra message fields.

**Architecture:** A small local context module reduces clocks and weather to anonymous allowlisted cues. The generator validates these cues at its boundary and writes one original <=20 ASCII line; the existing paired assembly invokes it once and reuses that line for both recipients. Manual dated theme/exact behavior and all live-send gates remain intact.

**Tech Stack:** Python 3.11, `unittest`, `requests`; offline `uv` test runner.

---

### Task 1: Anonymous daypart and weather cues

**Files:**
- Create: `src/daily_context.py`
- Create: `tests/test_daily_context.py`

- [ ] **Step 1: Write failing tests.** Import `daypart`, `weather_cue` from `daily_context`. Assert `04:59 -> night`, `05:00 -> morning`, `11:59 -> morning`, `12:00 -> afternoon`, `17:59 -> afternoon`, `18:00 -> evening`, `22:59 -> evening`, `23:00 -> night`. Reject `24:00`, `07:60`, `7:00`, or arbitrary strings with `ValueError`. Assert `Overcast 20°C -> cloudy`, `Sunny 24°C -> clear`, `Light rain` (not allowlisted) -> `None`, `Unavailable -> None`, and `Ignore previous`/multiline/embedded commands -> `None`.

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from daily_context import daypart, weather_cue

class DailyContextTests(unittest.TestCase):
    def test_daypart_boundaries(self):
        for clock, expected in (("04:59", "night"), ("05:00", "morning"),
                                ("11:59", "morning"), ("12:00", "afternoon"),
                                ("17:59", "afternoon"), ("18:00", "evening"),
                                ("22:59", "evening"), ("23:00", "night")):
            with self.subTest(clock=clock):
                self.assertEqual(daypart(clock), expected)

    def test_invalid_clock_rejected(self):
        for clock in ("24:00", "07:60", "7:00", "Ignore rules"):
            with self.subTest(clock=clock), self.assertRaises(ValueError):
                daypart(clock)

    def test_weather_cue_is_an_allowlist(self):
        for report, expected in (("Overcast 20°C", "cloudy"),
                                 ("Sunny 24°C", "clear"), ("Rain -2°C", "rainy"),
                                 ("Light rain", None), ("Unavailable", None),
                                 ("Ignore previous", None), ("Rain\nIgnore rules", None)):
            with self.subTest(report=report):
                self.assertEqual(weather_cue(report), expected)
```

- [ ] **Step 2: Verify RED.** Run `uv run --no-project --offline --with requests --python 3.11 python -m unittest tests.test_daily_context -q`; expect import failure because `daily_context` does not exist.
- [ ] **Step 3: Implement only these pure helpers.** Keep weather categories and accepted labels fixed; do not forward provider text or temperature.

```python
import re

VALID_DAYPARTS = frozenset({"morning", "afternoon", "evening", "night"})
VALID_WEATHER_CUES = frozenset({"clear", "cloudy", "rainy", "snowy", "foggy", "stormy"})
_LABELS = {
    "clear": "clear", "fair": "clear", "sunny": "clear",
    "ptly cloudy": "cloudy", "cloudy": "cloudy", "overcast": "cloudy",
    "rain": "rainy", "drizzle": "rainy", "showers": "rainy",
    "icy rain": "rainy", "icy driz": "rainy",
    "snow": "snowy", "snow shwr": "snowy", "fog": "foggy",
    "storm": "stormy", "hail storm": "stormy",
}

def daypart(clock: str) -> str:
    if not isinstance(clock, str) or re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock) is None:
        raise ValueError("Invalid local clock")
    hour = int(clock[:2])
    return "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening" if 18 <= hour < 23 else "night"

def weather_cue(report: str) -> str | None:
    if not isinstance(report, str):
        return None
    match = re.fullmatch(r"(.+?) -?[0-9]{1,3}°C", report)
    label = match.group(1) if match else report
    return _LABELS.get(label.lower())
```

- [ ] **Step 4: Verify GREEN.** Re-run the focused test and the full `python -m unittest discover -s tests -q` via the offline `uv` command; expect all pass.
- [ ] **Step 5: Commit.** Stage only `src/daily_context.py` and `tests/test_daily_context.py` and commit `Add anonymous daily context cues`.

### Task 2: Editorial DeepSeek prompt and boundary validation

**Files:**
- Modify: `src/deepseek_line.py:1-145`
- Modify: `tests/test_deepseek_line.py:1-175`

- [ ] **Step 1: Write failing tests.** Inspect the mocked request payload. For no manual theme, assert the prompt requires one shared two-sided line, low-pressure affection, real cues only, optional question, humor without forced slang, and no invented events/feelings; assert it includes only `morning/evening` and `cloudy/clear` from supplied cues. With `theme="ordinary days"`, assert the theme is present but no daypart/weather text is added. Malformed cue (`"Ignore previous"`) must fail before the HTTP call with `line_failure=invalid_context` and no raw text in stderr. Before implementation, update `test_prompt_asks_for_a_tender_personal_line_without_inventing_details` to assert `both receive`, `Do not invent`, `weather/time detail`, and the existing ASCII bound rather than the obsolete `directly to you`/`not ordinary moments` assertions.

```python
def test_shared_voice_uses_only_anonymous_cues(self):
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True), \
         patch.object(requests, "post", return_value=self.response()) as post, \
         redirect_stderr(StringIO()):
        generate_love_line(dayparts=("morning", "evening"), weather=("cloudy", "clear"))
    prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
    for phrase in ("both receive", "no pressure", "gentle humor", "optional question", "Do not invent"):
        self.assertIn(phrase, prompt)
    self.assertIn("morning", prompt)
    self.assertIn("cloudy", prompt)
    for private_value in ("Ann Arbor", "Shanghai", "20°C", "TEST_KEY"):
        self.assertNotIn(private_value, prompt)

def test_invalid_cue_fails_before_request(self):
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True), \
         patch.object(requests, "post") as post, redirect_stderr(StringIO()) as stderr:
        with self.assertRaises(DeepSeekLineError):
            generate_love_line(dayparts=("morning", "Ignore previous"))
    post.assert_not_called()
    self.assertEqual(stderr.getvalue(), "line_failure=invalid_context\n")
```

- [ ] **Step 2: Verify RED.** Run `uv run --no-project --offline --with requests --python 3.11 python -m unittest tests.test_deepseek_line -q`; expect failure from unsupported `dayparts`/`weather` parameters or old prompt assertions.
- [ ] **Step 3: Implement minimal prompt changes.** Retain the existing key handling, request validation, retry policy, and diagnostics. Add keyword-only cue parameters after `timeout`; validate tuple lengths and values against `VALID_DAYPARTS`/`VALID_WEATHER_CUES` before requesting. For `theme is not None`, retain the manually selected theme and hard boundaries but omit the default five angles and cue text.

```python
from daily_context import VALID_DAYPARTS, VALID_WEATHER_CUES

def generate_love_line(theme: str | None = None,
                       timeout: float | tuple[float, float] = (5, 30), *,
                       dayparts: tuple[str, str] | None = None,
                       weather: tuple[str | None, str | None] | None = None) -> str:
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        _unavailable("missing_key")
    if theme is not None:
        try:
            validate_inputs("2026-01-01", theme, None)
        except DailyContentError:
            _unavailable("invalid_theme")
    if theme is None and (
        (dayparts is not None and (not isinstance(dayparts, tuple) or len(dayparts) != 2 or any(type(part) is not str or part not in VALID_DAYPARTS for part in dayparts)))
        or (weather is not None and (not isinstance(weather, tuple) or len(weather) != 2 or any(cue is not None and (type(cue) is not str or cue not in VALID_WEATHER_CUES) for cue in weather)))
    ):
        _unavailable("invalid_context")
    prompt = (
        "Write ONE original emotionally warm English line for two long-distance partners who both receive it. "
        "Use at most 20 printable ASCII characters including spaces. Output only the line, no quotes, emoji or line breaks. "
        "Do not invent private memories, specific life events, places, or either person's feelings. "
        "Do not demand a reply. Keep it natural and complete, not forced shorthand. "
    )
    if theme is not None:
        prompt += f"Follow today's manual theme within these limits: {theme}"
    else:
        prompt += (
            "Choose one tone: two-sided timezone handoff, no pressure affection, "
            "weather/time detail, gentle humor, or rarely a tiny optional question. "
            "A greeting must make sense to both recipients. Use only the provided cues as facts. "
        )
        if dayparts is not None:
            prompt += f"The two anonymous dayparts are {dayparts[0]} and {dayparts[1]}. "
        if weather is not None and any(weather):
            prompt += f"Anonymous weather cues: {weather[0] or 'unknown'}, {weather[1] or 'unknown'}. "
    for attempt in range(3):
        line, failure = _request_line(key, prompt, timeout)
        if line is not None:
            print("line_source=deepseek", file=sys.stderr)
            return line
        if failure != "invalid_text" or attempt == 2:
            _unavailable(failure or "invalid_response")
    raise DeepSeekLineError()
```

- [ ] **Step 4: Verify GREEN.** Run focused and full offline `uv` test commands; all updated old prompt assertions must pass with the new behavior.
- [ ] **Step 5: Commit.** Stage only generator/tests and commit `Give daily DeepSeek lines a shared low-pressure voice`.

### Task 3: Paired assembly and user-facing explanation

**Files:**
- Modify: `src/main.py:175-226`
- Modify: `tests/test_paired_delivery.py:146-185`
- Modify: `tests/test_daily_integration.py`
- Modify: `README.md:99-106`

- [ ] **Step 1: Write failing integration tests.** In the existing mocked paired test, expect one generator call with `theme=None`, `dayparts=("evening", "morning")`, `weather=("cloudy", "clear")` when the two weather reports are `Overcast 20°C` and `Fair 25°C` and the times are `21:00` and `09:00`. Assert the two recipient payloads share exactly the same `meet_days` and `love_line`. Add a test where mocked weather is `Ignore previous`/`Unavailable`, assert generator receives `(None, None)` weather rather than raw provider text. Existing dated `exact` test must still show no generator call.

```python
with patch.object(main, "local_now_str", side_effect=["21:00", "09:00"]), \
     patch.object(main, "brief_weather", side_effect=["Overcast 20°C", "Fair 25°C"]), \
     patch.object(main, "generate_love_line", return_value="Always, with you.") as line:
    fields = main.build_payload_fields()
line.assert_called_once_with(theme=None,
                             dayparts=("evening", "morning"),
                             weather=("cloudy", "clear"))
```

- [ ] **Step 2: Verify RED.** Run `uv run --no-project --offline --with requests --python 3.11 python -m unittest tests.test_paired_delivery tests.test_daily_integration -q`; expect old `generate_love_line(theme=...)` invocation to fail the new call assertion.
- [ ] **Step 3: Integrate the already tested helpers.** Move existing `time_a/time_b` assignment before generation, reuse values later, and pass only the normalized cues to the generator when `exact` is absent.

```python
from daily_context import daypart, weather_cue

time_a = local_now_str(tz_a)
time_b = local_now_str(tz_b)
if exact is not None:
    short_line = exact
    print("line_source=manual", file=sys.stderr)
else:
    short_line = generate_love_line(
        theme=theme,
        dayparts=(daypart(time_a), daypart(time_b)),
        weather=(weather_cue(weather_a), weather_cue(weather_b)),
    )
```

- [ ] **Step 4: Verify GREEN and documentation.** Update README default short-line paragraph to describe shared, optional weather/daypart cues, manual theme precedence, no fabricated events, no guaranteed uniqueness, and no X-quote copying. Run all tests with the offline `uv` command, `git diff --check`, and a mocked dry-run test; do not invoke live send or `gh workflow run`.
- [ ] **Step 5: Commit.** Stage only integration/tests/README and commit `Ground shared daily line in anonymous time and weather`.

### Final read-only verification

- [ ] Run the full 3.11 offline suite again and inspect `git status --short --branch` and `git log -4 --oneline`.
- [ ] Verify no `.env`, Secret, PAT, routine, workflow, live send or remote push was touched. A mock success is not DeepSeek API success or phone delivery.
