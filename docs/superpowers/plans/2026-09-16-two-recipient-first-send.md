# Two-recipient WeChat first-send implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely send one current English weather/date message to Carlos and his girlfriend, including an approximate acquaintance count, then enable a separately gated CN daily send after phone receipt.

**Architecture:** Keep `SEND_MODE=dry-run` as default and preserve existing CN manual gating. Add a role-specific self manual path whose job can see only `WECHAT_OPENID_SELF`; keep CN's job limited to `WECHAT_OPENID_CN`. Reuse the existing template's `love_line` field for a two-line acquaintance note and love line, so the WeChat test-account template ID need not change. The confirmed `NEXT_MEET_DATE` continues its real countdown. Add a separate, default-off CN schedule path after verifying first sends.

**Tech Stack:** Python 3.11, stdlib `unittest`, `requests`, GitHub Actions YAML, GitHub CLI.

---

## File map

- `src/main.py`: assemble the extra acquaintance line; validate role-specific live context and pick exactly one recipient.
- `src/wechat.py`: avoid truncating the combined `love_line` value.
- `.github/workflows/daily-push.yml`: isolated `live-self` manual job, retain `live-cn`, then a separate CN schedule job gated by a default-off variable.
- `tests/test_stage_c.py`: exact payload, fail-closed behavior, Secret/job isolation and workflow checks.
- `README.md` and `config.example.env`: document the English message, two recipients, confirmed date and schedule gate.

### Task 1: Acquaintance count and current-template rendering

**Files:** Modify `src/main.py`, `src/wechat.py`, `tests/test_stage_c.py`.

- [ ] Add a failing `DateTests` case with patched `main.local_today` returning `date(2026, 9, 16)`, the normal weather/time/line mocks, `KNOWN_START_DATE=2019-09-02`, `LOVE_START_DATE=2026-07-08`, `NEXT_MEET_DATE=2026-12-20`. Assert `love_days == "71 days"`, `meet_days == "in 95 days"`, and `love_line == "Known: ≈2572 days\nThinking of you"`. Assert `wechat.build_template_data(fields)["love_line"]["value"]` is identical. Include an invalid `KNOWN_START_DATE=not-a-date` case which fails before `brief_weather` is called.
- [ ] Run `uv run --no-project --python 3.11 --with requests python -m unittest tests.test_stage_c.DateTests -v`; expect the new test to fail before implementation.
- [ ] In `build_payload_fields`, parse `KNOWN_START_DATE` using `date.fromisoformat(_env("KNOWN_START_DATE", "2019-09-02"))` before external calls. Calculate `known = love_days(known_start.isoformat(), today=today)` and set `love_line` to `f"Known: ≈{known} days\n{generate_love_line()}"`. Permit `≈` only in that field's fixed first line and `°` in weather; reject any other non-ASCII character. Set the `love_line` limit in `build_template_data` from 20 to 64.
- [ ] Run the focused tests and full suite with `uv run --no-project --python 3.11 --with requests python -m unittest discover -s tests -v`; expect all to pass, including existing English/attribution tests.
- [ ] Commit the payload and test changes.

### Task 2: Independent self recipient at application layer

**Files:** Modify `src/main.py`, `tests/test_stage_c.py`.

- [ ] Add failing tests for `LIVE_RECIPIENT=self`, `PUSH_SLOT=us`, `LIVE_CONFIRMATION=SEND_SELF_ONCE` in the existing owner/main/first-attempt `workflow_dispatch` context. Assert `main.resolve_openid()` returns the test self ID when both test IDs are present, and that CN context resolves only the CN ID. Assert missing role, swapped slot, wrong confirmation, schedule event, non-owner, wrong branch, retry and missing self ID fail before building weather or sending.
- [ ] Run the focused `SendModeTests`; expect the self path to fail before implementation.
- [ ] Change `validate_send_context` to require `LIVE_RECIPIENT` exactly `self` or `cn` for manual live, with `(self, us, SEND_SELF_ONCE)` or `(cn, cn, SEND_CN_ONCE)` as the only accepted triplets; preserve the repository/main/owner/first-attempt checks. Change `resolve_openid` to select only `WECHAT_OPENID_SELF` for self or `WECHAT_OPENID_CN` for cn, with no fallback.
- [ ] Run focused and full tests; expect all live context tests to pass.
- [ ] Commit application gating and tests.

### Task 3: Independent manual GitHub Actions job

**Files:** Modify `.github/workflows/daily-push.yml`, `tests/test_stage_c.py`, `README.md`, `config.example.env`.

- [ ] Add failing workflow tests that the manual choice includes `live-self`; `live-self` requires `slot=us` and exact `SEND_SELF_ONCE`; the self job loads `WECHAT_OPENID_SELF: ${{ secrets.WECHAT_OPENID_SELF }}` but contains no `WECHAT_OPENID_CN`; the CN job has the reverse; preview jobs contain neither; a schedule cannot enter either manual job. Update old tests which assert that *only* CN may load credentials to explicitly permit these two isolated jobs.
- [ ] Run `uv run --no-project --python 3.11 --with requests python -m unittest tests.test_stage_c.WorkflowPolicyTests -v`; expect failures before implementation.
- [ ] Add `mode=live-self` to the dispatch choices and validator; guard self exactly like CN for repository `carloshuangspec/wechat-ldr-daily-push`, `refs/heads/main`, actor/triggering actor `carloshuangspec`, and run attempt `1`. Add a `live-self` job with `if:` repeating those conditions, `PUSH_SLOT: us`, `SEND_MODE: live`, `LIVE_RECIPIENT: self`, `LIVE_CONFIRMATION: ${{ inputs.confirmation }}`, and only `WECHAT_OPENID_SELF` plus the three common WeChat Secrets. Set `LIVE_RECIPIENT: cn` on the existing CN job. Preserve both preview jobs as dry-run without WeChat Secrets.
- [ ] Update docs/example configuration for the self test, `KNOWN_START_DATE=2019-09-02`, the two-line English output and the fact that `2026-12-20` is confirmed. Run full tests, then `git diff --check`; expect no failures.
- [ ] Commit workflow and documentation changes.

### Task 4: Cloud preview and first live attempts

**Files:** No local file edits; GitHub Actions runs in `carloshuangspec/wechat-ldr-daily-push`.

- [ ] Inspect `git status`, local tests, `gh secret list -R carloshuangspec/wechat-ldr-daily-push` **names and timestamps only**, then push reviewed `main` commits. Confirm remote `main` SHA matches locally.
- [ ] Trigger `gh workflow run daily-push.yml -R carloshuangspec/wechat-ldr-daily-push -f mode=preview -f slot=both`; wait for the run; inspect only the redacted preview. Confirm both cities have fresh weather or explicit English fallback, `Together: 71 days` on 2026-09-16, `Known: ≈2572 days`, a complete love line, and a confirmed next-meeting countdown. If a preview is wrong, stop before any live dispatch.
- [ ] Trigger one `live-self`, `slot=us`, `confirmation=SEND_SELF_ONCE` manual run. Inspect status and only the whitelisted `errcode`/`msgid` result; do not print token, IDs or request body. If accepted, trigger one `live-cn`, `slot=cn`, `confirmation=SEND_CN_ONCE` manual run and inspect the same redacted result. If either fails, stop; do not automatically retry.
- [ ] Ask Carlos to check both phones, including newline and weather attribution. API acceptance is not phone receipt.

### Task 5: Prepare a default-off CN schedule; enable only after receipt

**Files:** Modify `.github/workflows/daily-push.yml`, `src/main.py`, `tests/test_stage_c.py`, `README.md`.

- [ ] Add failing tests for a separate `schedule-cn` live context: only `GITHUB_EVENT_NAME=schedule`, `GITHUB_EVENT_SCHEDULE=7 8 * * *`, canonical repo/main, `LIVE_RECIPIENT=cn`, `PUSH_SLOT=cn`, and `ENABLE_CN_DAILY=1` may send. Manual `SEND_CN_ONCE` must not enable schedule. Absent/other values of `ENABLE_CN_DAILY` and the US cron must fail before weather or send.
- [ ] Run focused tests to verify failure, then implement a separate schedule branch in `validate_send_context` and a `scheduled-cn` workflow job conditioned on `github.event_name == 'schedule' && github.event.schedule == '7 8 * * *' && vars.ENABLE_CN_DAILY == '1'`. Inject only the CN OpenID and common WeChat Secrets, plus `GITHUB_EVENT_SCHEDULE: ${{ github.event.schedule }}` and `ENABLE_CN_DAILY: ${{ vars.ENABLE_CN_DAILY }}`. Keep manual role checks independent. Preserve US preview-only and CN preview regardless of gate state.
- [ ] Run full tests and review job-level Secret isolation; commit and push the default-off schedule. Verify `ENABLE_CN_DAILY` is absent before and after push, so this preparation cannot cause a scheduled send. Leave the variable unset unless Carlos has confirmed both actual phone receipts. Once confirmed, set only repository variable `ENABLE_CN_DAILY=1` and verify its name/value (not a credential); do not trigger an extra manual send.
