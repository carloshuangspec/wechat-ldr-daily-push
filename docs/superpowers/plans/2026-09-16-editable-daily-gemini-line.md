# Editable Daily Gemini Line Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a fresh short English line through Gemini for each push, let Carlos specify one Shanghai-day theme or exact line, and fail safely rather than send an unintended fallback.

**Architecture:** `src/daily_content.py` validates the one dated JSON Secret and chooses `manual` or a Gemini theme; `src/gemini_line.py` talks to Gemini and rejects unsafe output; `main.py` captures one local date, assembles the message once, and verifies the rendered line is intact. A local `.command` editor streams the dated JSON into the GitHub Secret without a file or shell argument. Only CN jobs load that Secret and the existing live gates remain unchanged.

**Tech Stack:** Python 3.11, `requests`, `unittest`, GitHub Actions YAML, `gh` CLI.

---

## File map and constraints

- Create `src/daily_content.py`: strict parsing/selection and shared input validation.
- Modify `src/gemini_line.py`: API request, optional theme, full candidate validation; no static fallback.
- Modify `src/main.py` and `src/wechat.py`: Shanghai-day matching, single build/send, full `love_line` rendering, sanitized diagnostics.
- Create `scripts/edit_daily_message.py` plus `scripts/edit-daily-message.command`: interactive local edit and stdin-only Secret update.
- Modify `.github/workflows/daily-push.yml`, `README.md`, `config.example.env` and tests: CN-only Secret routing, scheduled preview suppression, usage instructions, regressions.

Use only the isolated `codex/gemini-api` worktree. Never read secret values or `.env`. Keep `ENABLE_CN_DAILY` unset/disabled, and never attempt a real send until deployment and the safe CN preview are independently verified. The complete behavior contract is `docs/superpowers/specs/2026-09-16-editable-daily-gemini-line-design.md`.

### Task 1: Validate one dated override

**Files:** Create `src/daily_content.py`; create `tests/test_daily_content.py`.

- [ ] **Step 1: Write a failing parser test.** Import `DailyContentError, parse_config, choose_line` and assert the following, then add separate cases for theme-only and missing configuration:

```python
config = parse_config('{"date":"2026-09-16","theme":"ordinary days","exact":"My favorite day"}')
self.assertEqual(config, {"date": "2026-09-16", "theme": "ordinary days", "exact": "My favorite day"})
self.assertEqual(choose_line(config, date(2026, 9, 16)), ("My favorite day", None, "manual", "active"))
self.assertEqual(choose_line(config, date(2026, 9, 17)), (None, None, "generated", "stale"))
self.assertEqual(choose_line(None, date(2026, 9, 16)), (None, None, "generated", "none"))
```
- [ ] **Step 2: Run `.venv/bin/python -m unittest tests.test_daily_content -v`;** expect missing-module failure caused by the new feature, not a typo.
- [ ] **Step 3: Implement `parse_config(raw: str) -> dict[str,str] | None`, `choose_line(config, shanghai_day: date) -> tuple[str | None,str | None,str,str]`, and `validate_inputs(day,theme,exact)` in `src/daily_content.py`.** Use `json.loads` with an `object_pairs_hook` that raises `DailyContentError` on duplicate keys, a `date.fromisoformat` round-trip for canonical `YYYY-MM-DD`, exact object keys `date/theme/exact`, optional nonempty strings, theme length <=120 with no controls/newlines, and exact <=20 ASCII printable characters without trimming. Reject an empty object, wrong JSON type, both texts absent, malformed JSON, wrong date type, and any unrecognized field with a *fixed* error message that cannot echo the JSON. Check configuration even when its date is stale. Choose exact before theme. Implement the selection body as:

```python
if config is None:
    return None, None, "generated", "none"
if config["date"] != shanghai_day.isoformat():
    return None, None, "generated", "stale"
if "exact" in config:
    return config["exact"], None, "manual", "active"
return None, config["theme"], "generated", "active"
```
- [ ] **Step 4: Add failing-then-passing table tests** for malformed/duplicate JSON, noncanonical dates, unknown keys, empty/missing texts, wrong types, theme control/length, exact non-ASCII/newline/length, both fields together, and Shanghai midnight date matching. For each new group run the targeted unittest first expecting a correct failure, then the minimal implementation, then `... -v` expecting PASS.
- [ ] **Step 5: Run `.venv/bin/python -m unittest discover -s tests -q`, `git diff --check`; commit** only this module and its tests with `feat: validate dated daily content`.

### Task 2: Generate safely or fail closed

**Files:** Modify `src/gemini_line.py`; modify the `GeminiTests` cases in `tests/test_stage_c.py` (leave other tests untouched).

- [ ] **Step 1: Replace fallback expectations with failing tests in `LoveLineTests`.** Missing `GEMINI_API_KEY`, timeout, non-200, redirect, invalid/missing candidates, abnormal finish, invalid full text, quoted wrapper, multiline, and >20/non-ASCII must raise `GeminiLineError` with a fixed message and never return static text. For example:

```python
with patch.dict(os.environ, {}, clear=True), patch.object(requests, "post") as post:
    with self.assertRaises(gemini_line.GeminiLineError):
        gemini_line.generate_love_line()
post.assert_not_called()
```

Existing valid mock response returns `"You are my home"` and logs exactly `gemini_source=generated` once. `generate_love_line(theme="ordinary days")` must include that text in the prompt; default prompt must not include private names/chats or assert today's events.
- [ ] **Step 2: Run `.venv/bin/python -m unittest tests.test_stage_c.LoveLineTests -v`;** expect failures for static fallback/current first-line extraction.
- [ ] **Step 3: Replace `_fallback` and `FALLBACK_LINES` with `GeminiLineError`.** Preserve the header-only API key and the pinned model/request settings. Build a generic English prompt with optional validated theme. Parse only a single candidate with `finishReason == 'STOP'` and one text part; trim *only ASCII spaces at either end*, then reject empty, >20 chars, non-ASCII/nonprintable, `\r`/`\n`, leading/trailing `'` or `"`, extra parts/prose. Convert response/network errors to a fixed `GeminiLineError` using `raise ... from None`, never print URL, response body, theme or key. Only log `gemini_source=generated` after valid result. Core validation is:

```python
line = text.strip(" ")
if (not line or len(line) > 20 or not line.isascii() or
        not line.isprintable() or line[0] in "\"'" or line[-1] in "\"'"):
    raise GeminiLineError("Gemini line unavailable") from None
```
- [ ] **Step 4: Run the targeted suite and then `.venv/bin/python -m unittest discover -s tests -q`.** Fix stale fallback assertions by changing expected behavior, not deleting coverage; verify no failing tests or raw error leaks.
- [ ] **Step 5: Run `git diff --check`; commit** generator and its test changes as `feat: fail closed on unsafe Gemini output`.

### Task 3: Assemble the one correct message

**Files:** Modify `src/main.py`, `src/wechat.py`; add `tests/test_daily_integration.py` and adjust relevant older assertions in `tests/test_stage_c.py`.

- [ ] **Step 1: Write failing integration tests.** With `PUSH_SLOT=cn`, a mocked Shanghai `today=date(2026,9,16)`, valid dated exact config, and stub weather/times, assert `build_payload_fields()` uses the exact line *without calling Gemini* and that `build_template_data(fields)['love_line']['value'] == fields['love_line']`; with a theme assert Gemini is called once with that theme; with stale config it is called once without a theme; with `PUSH_SLOT=us` assert CN-only override is ignored. Assert CN's `local_today` is called once and used for counters/override; assert generated failure makes `main()` return nonzero and never calls `send_template`. The preview metadata must include only Shanghai date and fixed override-status/source markers, not the raw theme.
- [ ] **Step 2: Run `.venv/bin/python -m unittest tests.test_daily_integration -v`;** expect the exact/Gemini bypass and fail-closed assertions to fail.
- [ ] **Step 3: Implement in `main.py`.** Capture `today = local_today(...)` once. Only for CN call `parse_config(os.getenv('DAILY_MESSAGE_CONFIG',''))` then `choose_line(config,today)`; for US always use no override. Log fixed `override_status=active|stale|none` plus CN day, and `gemini_source=manual` for exact, or call `generate_love_line(theme=theme)` once. Check assembled `love_line` is no more than 64 characters. Keep `_env` for ordinary variables, not for JSON. In `main()`, keep sanitized failures and ensure no send on payload or render exceptions. Preview metadata exposes no raw theme. Core selection:

```python
config = parse_config(os.getenv("DAILY_MESSAGE_CONFIG", "")) if slot == "cn" else None
exact, theme, source, status = choose_line(config, today)
line = exact if exact is not None else generate_love_line(theme=theme)
love_line = f"Known: ≈{known_days} days\n{line}"
if len(love_line) > 64:
    raise ConfigError("Love line exceeds template limit")
```
- [ ] **Step 4: In `wechat.py`, reject overlong `love_line` instead of `_short` truncation** while preserving truncation of other fields. After building template data, assert its `love_line` equals the original `fields['love_line']` before preview or send. Test a 65-character line is rejected, and no `...` is inserted by template rendering.
- [ ] **Step 5: Run `.venv/bin/python -m unittest discover -s tests -q` and `git diff --check`; commit** with `feat: honor CN daily override without truncation`.

### Task 4: Give Carlos a safe local editor

**Files:** Create `scripts/edit_daily_message.py`, `scripts/edit-daily-message.command`, `tests/test_daily_editor.py`.

- [ ] **Step 1: Write failing editor tests** using fake input/output and a mocked `subprocess.run`: default target date is `datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()`, valid theme/exact round-trip uses shared `validate_inputs`, confirmation is required, `subprocess.run` has argument vector `['gh','secret','set','DAILY_MESSAGE_CONFIG','-R','carloshuangspec/wechat-ldr-daily-push','--app','actions']`, `input` is JSON serialized to standard input (never in argv), `capture_output=True`, and no Secret text or subprocess stderr is printed; explicit clear uses only `['gh','secret','delete','DAILY_MESSAGE_CONFIG','-R',...,'--app','actions']` after confirmation. Reject blank theme+exact, bad date and invalid text without calling `gh`. Do not read existing Secret or write a temporary file.
- [ ] **Step 2: Run `.venv/bin/python -m unittest tests.test_daily_editor -v`;** expect missing-module failure.
- [ ] **Step 3: Implement a small `main()`** that locally prompts for date/theme/exact (both allowed; exact wins), previews exactly those entered values locally, asks an explicit yes before save, calls `gh` with a fixed argument list and `input=json.dumps({...},ensure_ascii=False)`, prints only success/fixed sanitized failure; `clear` is a separate explicit option and confirms deletion of only this Secret. Handle missing `gh`, nonzero exit and `KeyboardInterrupt` without claiming success. The `.command` wrapper should change to its repository parent and run `python3 scripts/edit_daily_message.py "$@"` without echoing values. Mark it executable. The secret-write call is exactly:

```python
subprocess.run(
    ["gh", "secret", "set", "DAILY_MESSAGE_CONFIG", "-R",
     "carloshuangspec/wechat-ldr-daily-push", "--app", "actions"],
    input=json.dumps(config, ensure_ascii=False), text=True,
    capture_output=True, check=False,
)
```
- [ ] **Step 4: Run targeted suite, full suite, and `git diff --check`; commit** with `feat: edit dated message without persisting plaintext`.

### Task 5: Route CN-only config and document truthful operation

**Files:** Modify `.github/workflows/daily-push.yml`, `README.md`, `config.example.env`, `tests/test_stage_c.py` or `tests/test_daily_workflow.py`.

- [ ] **Step 1: Write a failing workflow test.** Split YAML text at job headers and assert `DAILY_MESSAGE_CONFIG: ${{ secrets.DAILY_MESSAGE_CONFIG }}` exists exactly in `preview-cn`, `live-cn`, `scheduled-cn`, never in `preview-us` or `live-self`, and the scheduled `preview-cn` condition includes `vars.ENABLE_CN_DAILY != '1'`. Assert existing owner/branch/slot/attempt gates and `WECHAT_*` separation remain unchanged.
- [ ] **Step 2: Run `.venv/bin/python -m unittest tests.test_daily_workflow -v`;** expect routing/schedule failures.
- [ ] **Step 3: Update YAML** by adding `DAILY_MESSAGE_CONFIG: ${{ secrets.DAILY_MESSAGE_CONFIG }}` in the three CN message steps (not top-level, not tests), and change only the scheduled CN preview clause to `github.event_name == 'schedule' && github.event.schedule == '7 8 * * *' && vars.ENABLE_CN_DAILY != '1'`. Do not change `ENABLE_CN_DAILY` Variable or live confirmation. In README/config sample, replace fallback/optional-Key claims with fail-closed default, exact without Key, one-date Secret schema, Finder editor use, theme vs exact privacy, queue-time Secret capture, preview logs visibility, separate generation per run, and CN phone receipt/auto-send gates. Never put real intimate text or a Key in documentation.
- [ ] **Step 4: Run full unittest suite, `git diff --check`, inspect YAML guards and diff; commit** as `feat: route dated override to CN jobs only`.

### Task 6: Verify and deploy safely

**Files:** No new source files; status/log inspection only.

- [ ] **Step 1: Reread design spec and all task commits/diff against `origin/main`;** confirm no `.env`, credentials, unrelated edits, or daily-live gate changes. Have an independent spec reviewer and code-quality/security reviewer inspect the final diff and address significant issues.
- [ ] **Step 2: Run `.venv/bin/python -m unittest discover -s tests -q`, `git diff --check`, and validate GitHub Actions YAML.** Preserve exact test output/count and exit statuses.
- [ ] **Step 3: Inspect `gh secret list -R carloshuangspec/wechat-ldr-daily-push --json name,updatedAt` and `gh variable list ...` names/status only;** never read or print values. If no replacement Gemini Key, do not reuse the Key exposed in chat or trigger a doomed preview/live run.
- [ ] **Step 4: If code/tests/reviews are green, deploy code to remote main with non-force fast-forward only,** first verifying both worktree and main checkout statuses, upstream history, and remote confirmation. Rerun tests on merged main and verify remote SHA. Keep CN daily disabled.
- [ ] **Step 5: With a privately configured replacement Key, run one safe `mode=preview,slot=cn` on `main`;** inspect the actual `Preview CN` step's source/status without leaking values. Only if safe preview and all recipient Secrets are present, dispatch one `mode=live-cn,slot=cn,confirmation=SEND_CN_ONCE` on `main`, first attempt. Inspect only sanitized response. Do not rerun after ambiguous failure. An API `errcode=0/msgid` is acceptance, not phone receipt; ask Carlos to check Rachel's phone. If required config is absent, stop at that gate and describe precisely what remains.
