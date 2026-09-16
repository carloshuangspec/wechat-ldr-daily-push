# DeepSeek-Only Daily Line Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use DeepSeek for fresh English daily lines, offer one dated manual theme/exact choice, and skip any send whose line cannot be validated.

**Architecture:** The already completed `daily_content.py` chooses a dated CN override. `deepseek_line.py` alone calls the official Chat Completions endpoint. `main.py` assembles a line once; `wechat.py` refuses to truncate it. Only CN jobs load the daily override, while all message jobs use `DEEPSEEK_API_KEY`. The local editor streams one-day JSON directly to its GitHub Secret.

**Tech Stack:** Python 3.11, `requests`, `unittest`, GitHub Actions YAML, macOS `.command`, GitHub CLI.

---

Design: `docs/superpowers/specs/2026-09-16-deepseek-daily-line-design.md`; earlier Gemini implementation plan/provider choice superseded. Never read `.env`, clipboard contents or Secret values. All errors and logs must be sanitized. Work only in existing isolated branch, keep `ENABLE_CN_DAILY` off.

### Task 1: Date-bound override parser — completed

`src/daily_content.py` with `parse_config`, `choose_line`, `validate_inputs` and `tests/test_daily_content.py` committed in `3bf5fd5` + security fix `59176fc`. Review and full-suite verification still required before merge.

### Task 2: DeepSeek generator and safe output validation

**Files:** Create `src/deepseek_line.py`, `tests/test_deepseek_line.py`; remove runtime import/use of `src/gemini_line.py` in Task 3. Existing Gemini tests belong to historical coverage and will be rewritten to reflect new sole provider rather than deleting unrelated safety tests.

- [ ] **Step 1: Write failing `DeepSeekLineTests`.** Import `DeepSeekLineError, generate_love_line`; assert missing `DEEPSEEK_API_KEY` raises fixed exception before HTTP; a valid mock `{"choices":[{"finish_reason":"stop","message":{"content":"You are my home"}}]}` returns that text; `theme="ordinary days"` appears in request prompt only; rejected cases include 3xx/4xx/5xx, timeout, malformed JSON, zero or multiple choices, missing/non-`stop` finish, non-string/empty/multi-part or multiline/quoted/extra-prose/nonASCII/>20 text; none can return a fallback.

```python
with patch.dict(os.environ, {}, clear=True), patch.object(requests, "post") as post:
    with self.assertRaises(DeepSeekLineError):
        generate_love_line()
post.assert_not_called()
```

- [ ] **Step 2: Run `.venv/bin/python -m unittest tests.test_deepseek_line -v`;** expect red due to missing module.
- [ ] **Step 3: Implement `generate_love_line(theme: str | None = None, timeout=(5,30)) -> str`.** Fixed endpoint `https://api.deepseek.com/chat/completions`, headers `Authorization: Bearer <key>` (not query), `Content-Type: application/json`, JSON with model `deepseek-flash`, one user message, `thinking: {"type":"disabled"}`, `stream:false`. Keep TLS defaults and `allow_redirects=False`. Validate HTTP 200, exactly one choice with `finish_reason == "stop"`, `message.content` string. Strip only outer ASCII spaces, then require 1..20 ASCII printable and no quote wrapper/newline; reject extra commentary. For `invalid_text` only, make at most two additional generation requests before any send; never retry an HTTP/auth/network failure or any WeChat send. Convert errors to fixed `DeepSeekLineError` without response body/URL/exception chain, print only `line_source=deepseek` on success and a fixed `line_failure` category on failure. Prompt generic English two independent lives/ordinary days and optional validated short theme; no names/archive/events.

```python
response = requests.post(
    "https://api.deepseek.com/chat/completions",
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    json={"model": "deepseek-flash", "messages": [{"role": "user", "content": prompt}],
          "thinking": {"type": "disabled"}, "stream": False},
    timeout=(5, 30), allow_redirects=False,
)
```

- [ ] **Step 4: Rerun targeted tests green, full suite after Task 3, `git diff --check`; commit** generator/test only.

### Task 3: Assemble, render and fail safely

**Files:** Modify `src/main.py`, `src/wechat.py`, `tests/test_stage_c.py`; create `tests/test_daily_integration.py`.

- [ ] **Step 1: Write failing integration tests** for matching CN exact (no API), theme (API called once with theme), stale config (API once generic), US ignores CN override, Shanghai local date captured once, sanitized malformed-config error, API failure => no `send_template`, full two-line `love_line` survives rendering and >64 rejects before preview/send. Update older tests that mock Gemini to mock DeepSeek and expect `line_source=deepseek`; do not drop safety coverage.
- [ ] **Step 2: Run `.venv/bin/python -m unittest tests.test_daily_integration -v`;** expect red.
- [ ] **Step 3: In `main.py`,** capture `today` once, only parse `DAILY_MESSAGE_CONFIG` for CN, choose exact/theme, and call `generate_love_line(theme=theme)` only if no exact. Print `override_status=active|stale|none` and Shanghai date for CN, `line_source=manual` for exact (generator prints DeepSeek marker only for API success). Reject full field >64 and any non-English generated text. Keep send gating and sanitized generic errors. Use `build_template_data` before output or send and assert returned `love_line.value == fields['love_line']`.

```python
config = parse_config(os.getenv("DAILY_MESSAGE_CONFIG", "")) if slot == "cn" else None
exact, theme, source, status = choose_line(config, today)
line = exact if exact is not None else generate_love_line(theme=theme)
love_line = f"Known: ≈{known_days} days\n{line}"
if len(love_line) > 64:
    raise ConfigError("Love line exceeds template limit")
```

- [ ] **Step 4: In `wechat.py`,** reject `love_line` >64 rather than truncate, preserving other fields' existing behavior. Run targeted tests, then `.venv/bin/python -m unittest discover -s tests -q` and `git diff --check`; commit.

### Task 4: Local date/theme/exact editor

**Files:** Create `scripts/edit_daily_message.py`, executable `scripts/edit-daily-message.command`, `tests/test_daily_editor.py`.

- [ ] **Step 1: Write failing tests** for Shanghai date default, shared `validate_inputs`, local confirmation/cancel/clear, stdin-only write with fixed argv, no argv/log/file leaks, sanitized failed/missing `gh`. Run `.venv/bin/python -m unittest tests.test_daily_editor -v` and observe red.
- [ ] **Step 2: Implement local prompts** for date/theme/exact (both allowed exact wins); display entered text locally, require yes, call `subprocess.run` with `input=json.dumps(config, ensure_ascii=False), text=True, capture_output=True, check=False`. Fixed argv is:

```python
["gh", "secret", "set", "DAILY_MESSAGE_CONFIG", "-R",
 "carloshuangspec/wechat-ldr-daily-push", "--app", "actions"]
```

Separate deliberate clear option confirms then uses `gh secret delete DAILY_MESSAGE_CONFIG -R ... --app actions`. Finder wrapper changes to repo parent and runs `python3 scripts/edit_daily_message.py "$@"`. No file/history/command-argument containing config. Run targeted/full tests green, diff check, commit.

### Task 5: Wire jobs and instructions

**Files:** Modify `.github/workflows/daily-push.yml`, `README.md`, `config.example.env`; create `tests/test_daily_workflow.py`.

- [ ] **Step 1: Write failing job-scoped YAML text tests**: `DAILY_MESSAGE_CONFIG: ${{ secrets.DAILY_MESSAGE_CONFIG }}` only in preview-cn/live-cn/scheduled-cn, `DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}` in all five message steps, no job acquires Gemini Key, US/SELF never acquire CN override, scheduled preview-cn suppressed when `vars.ENABLE_CN_DAILY == '1'`, three live gates unchanged. Run targeted tests red.
- [ ] **Step 2: Apply just those YAML changes.** Replace README/config references to Gemini fallback with DeepSeek sole provider, strict one-day editor, actual API vs mock logs, Key/private data/preview visibility, queue-time Secret snapshot, skip-on-error, daily-live off and phone receipt boundary. Tests/preview steps must not acquire `WECHAT_*`; keep existing owner/ref/attempt/confirmation checks.
- [ ] **Step 3: Run all tests green, `git diff --check`, YAML parse/guard checks; commit.**

### Task 6: Verify, deploy, then one controlled send

- [ ] **Step 1: Independent spec and code-quality/security reviews of the entire diff; fix all important findings.** Verify full suite, no secrets in git/diff/logs and no unrequested live enablement.
- [ ] **Step 2: Check GitHub Secret/Variable names and updated times only** (`DEEPSEEK_API_KEY` now exists, still untested); no `.env` or clipboard inspection. Fast-forward main only if both checkouts clean, upstream unchanged, and tests pass; push non-force, verify remote SHA and main tests.
- [ ] **Step 3: Trigger `mode=preview,slot=cn` on remote main** without an active exact override to prove DeepSeek API generation; inspect only actual `Preview CN` step's `line_source=deepseek` and safe rendered content. If preview fails, stop without live. Verify live required Secret names and daily gate off.
- [ ] **Step 4: If preview green and content appropriate, trigger one `mode=live-cn,slot=cn,confirmation=SEND_CN_ONCE` on remote main.** Inspect sanitized WeChat result without auto-retry, and request phone receipt confirmation. Do not enable `ENABLE_CN_DAILY` without separate user decision.
