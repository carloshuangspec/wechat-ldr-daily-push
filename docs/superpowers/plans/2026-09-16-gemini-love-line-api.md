# Gemini Love-Line API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing English love-line generator use a current stable Gemini model with header-based authentication and an observable, non-secret preview result.

**Architecture:** Keep `src/gemini_line.py` as the only Gemini HTTP boundary and preserve its string return type and English fallback. Existing GitHub Actions jobs already pass the optional Secret and model variable; only the generator, its tests, and configuration docs need changes. The preview log prints a fixed generated/fallback marker, never request data or error bodies.

**Tech Stack:** Python 3.11+, `requests`, `unittest`, existing GitHub Actions workflow.

---

### Task 1: Stable model and safe request

**Files:**
- Modify: `tests/test_stage_c.py:699-712`
- Modify: `src/gemini_line.py:39-62`

- [ ] **Step 1: Add the failing request-shape test.** Extend `LoveLineTests` with the following behavior (place it beside the existing mocked successful-response test); use another `patch.dict` call with `GEMINI_MODEL=gemini-3.6-flash` to assert the override URL while retaining the header. Set `status_code=200` on all existing successful Gemini response mocks.

```python
response = Mock()
response.status_code = 200
response.raise_for_status.return_value = None
response.json.return_value = {
    "candidates": [{"content": {"parts": [{"text": "You are my home"}]}}]
}
with patch.dict(os.environ, {"GEMINI_API_KEY": "TEST_KEY"}, clear=True), patch.object(
    requests, "post", return_value=response
) as post:
    self.assertEqual(gemini_line.generate_love_line(), "You are my home")
    self.assertEqual(
        post.call_args.args[0],
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
    )
    self.assertEqual(post.call_args.kwargs["headers"], {"x-goog-api-key": "TEST_KEY"})
    self.assertNotIn("params", post.call_args.kwargs)
    self.assertIs(post.call_args.kwargs["allow_redirects"], False)
```

For a redirect response with `response.status_code = 302`, keep a fake valid candidate and assert a fallback line; `raise_for_status()` alone does not reject redirects.
- [ ] **Step 2: Watch it fail for the intended reason.** Run `.venv/bin/python -m unittest tests.test_stage_c.LoveLineTests -v`; expected: assertions fail on the old default URL or missing `headers`, not on import/setup errors.
- [ ] **Step 3: Make the smallest generator change.** Replace the old default and request arguments with the following, and reject a non-200 response before parsing its body. Preserve the existing prompt, filtering, and fallback.

```python
model = (os.getenv("GEMINI_MODEL") or "gemini-3.8-flash").strip()
response = requests.post(
    url,
    headers={"x-goog-api-key": api_key},
    json=payload,
    timeout=timeout,
    allow_redirects=False,
)
response.raise_for_status()
if response.status_code != 200:
    return _fallback()
```
- [ ] **Step 4: Verify.** Run `.venv/bin/python -m unittest tests.test_stage_c.LoveLineTests -v`; expected: request-shape and preexisting love-line tests pass.
- [ ] **Step 5: Commit only the tested generator and test change.** Run `git add src/gemini_line.py tests/test_stage_c.py` and `git commit -m "Fix Gemini model and header authentication"`.

### Task 2: Avoid silent empty/truncated output with Gemini 3.8

**Files:**
- Modify: `tests/test_stage_c.py:690-800`
- Modify: `src/gemini_line.py:49-75`

- [ ] **Step 1: Add failing generation-config and truncation tests.** With a dummy `TEST_KEY` and a mocked valid 200 candidate, assert the `requests.post` JSON has `generationConfig.thinkingConfig.thinkingLevel == "low"`, `maxOutputTokens == 512`, and no `temperature`. Separately, make a mocked 200 response with `finishReason == "MAX_TOKENS"` and even a 20-character-or-less `text`, and assert the generator returns an existing English fallback line. A normal candidate with `finishReason == "STOP"` must still yield its valid English line.

```python
config = post.call_args.kwargs["json"]["generationConfig"]
self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "low"})
self.assertEqual(config["maxOutputTokens"], 512)
self.assertNotIn("temperature", config)
response.json.return_value = {
    "candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "You are my home"}]}}]
}
self.assertIn(gemini_line.generate_love_line(), gemini_line.FALLBACK_LINES)
```

- [ ] **Step 2: Watch intended failures.** Run `.venv/bin/python -m unittest tests.test_stage_c.LoveLineTests -v`; expected: config assertion and truncated-candidate test fail against the existing behavior.
- [ ] **Step 3: Implement only the config/finish guard.** Replace the old config and reject truncation before parsing the first candidate's content. Preserve all other authentication, prompt, and validation behavior.

```python
"generationConfig": {
    "thinkingConfig": {"thinkingLevel": "low"},
    "maxOutputTokens": 512,
},
# After candidates is known non-empty:
if candidates[0].get("finishReason") == "MAX_TOKENS":
    return _fallback()
```

- [ ] **Step 4: Verify and commit.** Run `.venv/bin/python -m unittest discover -s tests -v`, then `git add src/gemini_line.py tests/test_stage_c.py` and `git commit -m "Avoid truncated Gemini love lines"` only after the suite passes.

### Task 3: Accept only normally finished Gemini text

**Files:**
- Modify: `tests/test_stage_c.py:690-810`
- Modify: `src/gemini_line.py:68-82`

- [ ] **Step 1: Add failing finish-reason tests.** Make every mocked successfully generated candidate explicitly include `finishReason: "STOP"`. Add a parameterized test where a 200 response carries a valid short English text with each of `SAFETY`, `RECITATION`, `SPII`, `OTHER`, and no `finishReason`; assert fallback for all. Keep the existing `MAX_TOKENS` and `STOP` tests.

```python
for reason in ("SAFETY", "RECITATION", "SPII", "OTHER", None):
    response = self.successful_response()
    if reason is not None:
        response.json.return_value["candidates"][0]["finishReason"] = reason
    with self.subTest(reason=reason), patch.dict(
        os.environ, {"GEMINI_API_KEY": "TEST_KEY"}, clear=True
    ), patch.object(requests, "post", return_value=response):
        self.assertIn(gemini_line.generate_love_line(), gemini_line.FALLBACK_LINES)
```

- [ ] **Step 2: Watch failure.** Run `.venv/bin/python -m unittest tests.test_stage_c.LoveLineTests -v`; expected: the abnormal/missing finish-reason cases return the generated line, failing the new test.
- [ ] **Step 3: Make the smallest guard change.** Replace the first-candidate check with:

```python
if candidate.get("finishReason") != "STOP":
    return _fallback()
```

- [ ] **Step 4: Verify and commit.** Run `.venv/bin/python -m unittest discover -s tests -v`; expected: all tests pass. Commit only `src/gemini_line.py` and `tests/test_stage_c.py` as `Reject abnormally finished Gemini text`.

### Task 4: Distinguish real generation from fallback without leaking data

**Files:**
- Modify: `tests/test_stage_c.py:690-748`
- Modify: `src/gemini_line.py:5-30,63-84`

- [ ] **Step 1: Add failing diagnostic tests.** In `LoveLineTests`, capture stderr with `redirect_stderr(StringIO())`: with no key, assert a fallback line plus exactly `gemini_source=fallback`; with a mocked valid API result, assert the generated line plus exactly `gemini_source=generated`; with a mocked `requests.Timeout`, assert a fallback line plus exactly `gemini_source=fallback`. Use only dummy `TEST_KEY` in tests. For each case use the same check:

```python
stderr = StringIO()
with redirect_stderr(stderr):
    line = gemini_line.generate_love_line()
self.assertIn(line, gemini_line.FALLBACK_LINES)  # For fallback cases only.
self.assertEqual(stderr.getvalue().strip(), "gemini_source=fallback")
```
- [ ] **Step 2: Watch the tests fail.** Run `.venv/bin/python -m unittest tests.test_stage_c.LoveLineTests -v`; expected: missing fixed diagnostic lines, not an import/setup error.
- [ ] **Step 3: Add fixed, non-secret diagnostics.** Import `sys`; add only these two statements at the described return points. Never print the key, exception text, API body, or full prompt.

```python
print("gemini_source=fallback", file=sys.stderr)  # Inside _fallback().
print("gemini_source=generated", file=sys.stderr)  # Before valid generated return.
```
- [ ] **Step 4: Verify all tests.** Run `.venv/bin/python -m unittest discover -s tests -v`; expected: all tests pass, including send gates.
- [ ] **Step 5: Commit only generator/test changes.** Run `git add src/gemini_line.py tests/test_stage_c.py` and `git commit -m "Report safe Gemini generation provenance"`.

### Task 5: Configuration docs and preview boundary

**Files:**
- Modify: `config.example.env:18-22`
- Modify: `README.md:72-89`

- [ ] **Step 1: Update examples and documentation.** Change the commented model example to `# GEMINI_MODEL=gemini-3.8-flash`. Add this text near the README Gemini paragraph: "Default Gemini model: `gemini-3.8-flash` (stable); `GEMINI_MODEL` overrides it. Preview logs `gemini_source=generated` only for a valid Gemini line and `gemini_source=fallback` otherwise. The previously chat-exposed key must be revoked; store a new key only as the Actions Secret `GEMINI_API_KEY`. Never paste a key into this repository or chat." Keep `ENABLE_CN_DAILY` absent and do not run a live WeChat mode.
- [ ] **Step 2: Verify documentation and full regression suite.** Run `git diff --check` and `.venv/bin/python -m unittest discover -s tests -v`; expected: whitespace check succeeds and all tests pass.
- [ ] **Step 3: Commit only docs.** Run `git add config.example.env README.md` and `git commit -m "Document safe Gemini API setup and preview"`.
- [ ] **Step 4: After Carlos privately saves a newly generated key, push the reviewed code and trigger only `mode=preview, slot=both`; verify successful jobs, `gemini_key_set: true`, and `gemini_source=generated` in safe logs.** Without the new Secret, do not claim real API success. Do not start any `live-*` mode or set `ENABLE_CN_DAILY`.

## Environment setup and security

In the isolated checkout, create a `.venv` and run `.venv/bin/python -m pip install -r requirements.txt` before the first test; `.venv/` is ignored. Do not read `.env`, use the key pasted into chat, put a key in test fixtures, print a key, or run the user-supplied curl. The existing fake test string `TEST_KEY` is not a credential. If the user has not rotated and installed a new key, stop after local tests and clearly mark remote real-API preview as pending.
