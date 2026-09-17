# Grok-Owned Daily Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Grok trigger one shared CN+SELF WeChat message at Shanghai 09:00 through GitHub Actions without retaining WeChat/DeepSeek keys or creating duplicate automatic sends.

**Architecture:** Keep the current shared payload and two sequential send calls. Add a dedicated dispatch mode and a secret-free claim job that atomically creates one date-named Git ref before a read-only sender job can run. Stage the code while the existing schedule continues, prove Grok can trigger a credential-free preview, then remove the schedule and activate only Grok's daily routine. A separate read-only monitor reports missing or partial sends but never retries them.

**Tech Stack:** Python 3.11, `requests`, stdlib `unittest`, GitHub Actions YAML and GitHub REST API, Grok Bot routine/cloud computer.

---

## File map

- Create `src/daily_claim.py`: validate Shanghai date and atomically claim `refs/tags/ldr-daily-YYYY-MM-DD`; no message or recipient credentials.
- Create `tests/test_daily_claim.py`: mocked HTTP claim, duplicate, ambiguous error and redaction behavior.
- Modify `src/main.py`: accept only the claimed paired dispatch context; recheck Shanghai date before any live send, retaining the existing single shared payload and CN→SELF order.
- Modify `.github/workflows/daily-push.yml`: add `daily-both` input, `delivery_date` and isolated claim job; make paired send depend on its output; later remove the old schedule source and schedule-only jobs.
- Modify `tests/test_paired_delivery.py`, `tests/test_daily_schedule.py`, `tests/test_daily_workflow.py`, `tests/test_stage_c.py`: new dispatch and claim gates, staged/retired schedule assertions, unchanged manual/preview credential isolation.
- Modify `README.md`: operation, permission, no-retry and receipt boundaries.
- External Grok UI only after code passes: store a new single-repo Actions-write PAT in its secure form, prove preview, change the read-only monitor, then enable the Grok sender routine. Never read, echo or save the PAT value locally.

Run all local tests with `uv run --no-project --python 3.11 --with requests python -m unittest discover -s tests -q`; plain system `python3` lacks `requests` on this Mac. Baseline before edits: 146 tests pass. All `TEST_*` values below are invented test doubles, not actual credentials.

### Task 1: Date claim without secrets

**Files:** Create `tests/test_daily_claim.py`, `src/daily_claim.py`.

- [ ] **Step 1: Write failing tests.** Add `DailyClaimTests` using `unittest.mock.Mock`: fixed `now=date(2026, 9, 17)`, canonical repo, 40-character dummy SHA and token `TEST_TOKEN`. Mock `requests.post` returning `201` plus `{"ref":"refs/tags/ldr-daily-2026-09-17"}` and assert `claim(...)=True`, exact `POST /repos/carloshuangspec/wechat-ldr-daily-push/git/refs`, `allow_redirects=False`, and no GET. For `422` or `409`, mock GET exact `/git/ref/tags/ldr-daily-2026-09-17` returning the exact `ref` and assert `False`; with GET `404`, wrong `ref`, or GET timeout assert `ClaimError`. Assert bad date, different day, wrong repo, empty token and invalid SHA fail before any HTTP. Capture stderr for a POST timeout and assert neither fake token nor HTTP response body appears. Example test body:

```python
post = Mock(status_code=201)
post.json.return_value = {"ref": "refs/tags/ldr-daily-2026-09-17"}
http = Mock(post=Mock(return_value=post), get=Mock())
self.assertTrue(daily_claim.claim("2026-09-17", "carloshuangspec/wechat-ldr-daily-push", "a" * 40, "TEST_TOKEN", http=http, now=date(2026, 9, 17)))
http.get.assert_not_called()
```

- [ ] **Step 2: Prove red.** Run `uv run --no-project --python 3.11 --with requests python -m unittest tests.test_daily_claim -v`; expect import failure because `daily_claim` does not exist.

- [ ] **Step 3: Implement the isolated claim.** In `src/daily_claim.py` use the complete interface below. The CLI writes `claimed=true|false` and `day=YYYY-MM-DD` only to `GITHUB_OUTPUT`; its console output is fixed, never an exception/response/token. A failed or ambiguous creation exits nonzero without sending and without retry.

```python
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

REPO = "carloshuangspec/wechat-ldr-daily-push"


class ClaimError(ValueError):
    pass


def claim(day: str, repo: str, sha: str, token: str, *, http=requests, now: date | None = None) -> bool:
    today = now or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    try:
        valid_day = date.fromisoformat(day).isoformat() == day and day == today.isoformat()
    except ValueError:
        valid_day = False
    if repo != REPO or not valid_day or re.fullmatch(r"[0-9a-f]{40}", sha) is None or not token:
        raise ClaimError("invalid claim context")
    ref = f"refs/tags/ldr-daily-{day}"
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"}
    base = f"https://api.github.com/repos/{REPO}/git"
    try:
        made = http.post(f"{base}/refs", headers=headers, json={"ref": ref, "sha": sha}, timeout=10, allow_redirects=False)
        if made.status_code == 201 and made.json().get("ref") == ref:
            return True
        if made.status_code in (409, 422):
            found = http.get(f"{base}/ref/tags/ldr-daily-{day}", headers=headers, timeout=10, allow_redirects=False)
            if found.status_code == 200 and found.json().get("ref") == ref:
                return False
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        pass
    raise ClaimError("claim unavailable")


def main() -> int:
    try:
        day = os.getenv("DELIVERY_DATE") or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        claimed = claim(day, os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_SHA", ""), os.getenv("GH_TOKEN", ""))
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"claimed={str(claimed).lower()}\nday={day}\n")
    except (ClaimError, OSError, KeyError):
        print("daily_claim_failed", file=sys.stderr)
        return 2
    print(f"daily_claim={'created' if claimed else 'exists'} day={day}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Prove green and inspect logs.** Run focused tests and `git diff --check`; expect all focused cases to pass and no token/response text in stdout/stderr assertions.
- [ ] **Step 5: Commit.** `git add src/daily_claim.py tests/test_daily_claim.py && git commit -m 'Add fail-closed Shanghai-day delivery claim'`.

### Task 2: Application-level paired dispatch gate

**Files:** Modify `tests/test_paired_delivery.py`, `src/main.py`.

- [ ] **Step 1: Write failing dispatch tests.** Extend the paired fixture with `DAILY_CLAIM_CREATED=true`, `DAILY_CLAIM_DATE=2026-09-17`; patch `main.local_today` to return `date(2026,9,17)` in each paired live test. Add a dispatch fixture with `GITHUB_EVENT_NAME=workflow_dispatch`, `GITHUB_ACTOR=GITHUB_TRIGGERING_ACTOR=carloshuangspec`, `LIVE_DISPATCH_MODE=daily-both`, `LIVE_DISPATCH_SLOT=both`, `LIVE_DISPATCH_DATE=2026-09-17`. Assert it passes and that each altered field, missing claim, wrong date, either disabled daily switch, wrong repo/ref/actor, second attempt or swapped slot fails before `build_payload_fields` and `send_template`. Example:

```python
with patch.dict(os.environ, DISPATCH_ENV, clear=True), patch.object(main, "local_today", return_value=date(2026, 9, 17)):
    main.validate_send_context("live", "cn")
for key, value in (("DAILY_CLAIM_CREATED", "false"), ("LIVE_DISPATCH_DATE", "2026-09-18"), ("GITHUB_RUN_ATTEMPT", "2")):
    with self.subTest(key=key), patch.dict(os.environ, {**DISPATCH_ENV, key: value}, clear=True), patch.object(main, "local_today", return_value=date(2026, 9, 17)):
        with self.assertRaises(main.ConfigError):
            main.validate_send_context("live", "cn")
```

- [ ] **Step 2: Prove red.** Run `uv run --no-project --python 3.11 --with requests python -m unittest tests.test_paired_delivery -v`; expect new dispatch acceptance and claim-rejection tests to fail.
- [ ] **Step 3: Implement the narrow gate.** Keep the current single-recipient manual branches. Just after verifying `GITHUB_ACTIONS=true`, require `DAILY_CLAIM_CREATED=true`, exact date and both flags only when `recipient == 'both'`; leave the schedule branch for the staging release. Replace its unconditional paired dispatch rejection with the following check:

```python
if recipient == "both":
    day = _env("DAILY_CLAIM_DATE")
    if _env("DAILY_CLAIM_CREATED") != "true" or day != local_today("Asia/Shanghai").isoformat():
        raise ConfigError("daily claim context invalid")
    if os.getenv("ENABLE_CN_DAILY") != "1" or os.getenv("ENABLE_SELF_DAILY") != "1":
        raise ConfigError("daily switches disabled")
    if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
        expected = {
            "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_ACTOR": "carloshuangspec",
            "GITHUB_TRIGGERING_ACTOR": "carloshuangspec",
            "GITHUB_RUN_ATTEMPT": "1",
            "LIVE_DISPATCH_MODE": "daily-both",
            "LIVE_DISPATCH_SLOT": "both",
            "LIVE_DISPATCH_DATE": day,
        }
        if any(_env(key) != value for key, value in expected.items()):
            raise ConfigError("paired dispatch context invalid")
        return
```

In `build_payload_fields`, use `local_today('Asia/Shanghai')` for a paired message and assert it matches `_env('DAILY_CLAIM_DATE')` when `SEND_MODE=live`; retain the existing slot-local date for singles/preview. In `main`, after building but before the first `send_template`, recheck the Shanghai date for live paired sends; if changed, return `2` with a fixed redacted error. Do not regenerate per-recipient fields or retry either send.

- [ ] **Step 4: Prove green.** Run focused paired tests, `tests.test_daily_schedule`, and full suite; update existing paired tests' `local_today` call-count expectation to reflect gate/build/pre-send checks. All existing single-recipient tests must still pass.
- [ ] **Step 5: Commit.** `git add src/main.py tests/test_paired_delivery.py && git commit -m 'Gate claimed paired workflow dispatch at application layer'`.

### Task 3: Stage a dedicated GitHub claim and dispatch route

**Files:** Modify `.github/workflows/daily-push.yml`, `tests/test_paired_delivery.py`, `tests/test_daily_workflow.py`, `tests/test_stage_c.py`, `README.md`.

- [ ] **Step 1: Write failing workflow-policy tests.** Assert `workflow_dispatch.inputs.mode.options` contains `daily-both`, `delivery_date` has optional default `""`; the validator checks slot `both`, blank confirmation, both flags, owner/main/first attempt and current Shanghai date. Assert `claim-daily` has `permissions: contents: write`, no `WECHAT_*`/`DEEPSEEK_API_KEY`, and `daily-both` needs `claim-daily` with `claimed == 'true'`, both OpenIDs, `DAILY_CLAIM_DATE` and mode/date context. Assert preview jobs still have no WeChat credentials. Replace brittle test slicing at the new job boundary; retain stage-specific old-schedule checks until Task 5. Example:

```python
workflow = WORKFLOW.read_text(encoding="utf-8")
claim_job = workflow.split("  claim-daily:\n", 1)[1].split("  daily-both:\n", 1)[0]
send_job = workflow.split("  daily-both:\n", 1)[1]
self.assertIn("contents: write", claim_job)
self.assertNotIn("WECHAT_APP_SECRET:", claim_job)
self.assertIn("needs.claim-daily.outputs.claimed == 'true'", send_job)
self.assertIn("WECHAT_OPENID_CN: ${{ secrets.WECHAT_OPENID_CN }}", send_job)
self.assertIn("WECHAT_OPENID_SELF: ${{ secrets.WECHAT_OPENID_SELF }}", send_job)
```

- [ ] **Step 2: Prove red.** Run focused workflow tests; expect missing mode/job/output assertions to fail.
- [ ] **Step 3: Stage the YAML route.** Add optional `delivery_date` input so existing manual/preview requests need no extra input; the `daily-both` validator case must use `TZ=Asia/Shanghai date +%F`, require exact `YYYY-MM-DD`, both flags, repo/ref/actor/triggering_actor, `run_attempt=1`, blank confirmation and `slot=both`. Keep the schedule source until Grok preview is proven. Insert secret-free `claim-daily` after validation and before paired send; change the existing paired sender ID to `daily-both`, with both schedule and exact dispatch sources guarded. Use these concrete anchors:

```yaml
      delivery_date:
        description: "Shanghai day YYYY-MM-DD; daily-both only"
        required: false
        default: ""
        type: string
```

```bash
daily-both)
  if [ "$REQUEST_SLOT" != both ] || [ -n "$REQUEST_CONFIRMATION" ] ||
     [ "$REQUEST_DAY" != "$(TZ=Asia/Shanghai date +%F)" ] ||
     [ "$ENABLE_CN_DAILY" != 1 ] || [ "$ENABLE_SELF_DAILY" != 1 ] ||
     [ "$REQUEST_REPOSITORY" != carloshuangspec/wechat-ldr-daily-push ] ||
     [ "$REQUEST_REF" != refs/heads/main ] ||
     [ "$REQUEST_ACTOR" != carloshuangspec ] ||
     [ "$REQUEST_TRIGGERING_ACTOR" != carloshuangspec ] || [ "$REQUEST_ATTEMPT" != 1 ]; then
    echo "::error::daily-both context invalid"; exit 1
  fi
  ;;
```

The corresponding `validate-dispatch` step `env` adds these exact entries:

```yaml
          REQUEST_DAY: ${{ inputs.delivery_date }}
          ENABLE_CN_DAILY: ${{ vars.ENABLE_CN_DAILY }}
          ENABLE_SELF_DAILY: ${{ vars.ENABLE_SELF_DAILY }}
```

```yaml
  claim-daily:
    needs: validate-dispatch
    if: >
      needs.validate-dispatch.result == 'success' &&
      vars.ENABLE_CN_DAILY == '1' && vars.ENABLE_SELF_DAILY == '1' &&
      github.repository == 'carloshuangspec/wechat-ldr-daily-push' &&
      github.ref == 'refs/heads/main' && github.run_attempt == '1' &&
      ((github.event_name == 'schedule' && github.event.schedule == '0 9 * * *') ||
       (github.event_name == 'workflow_dispatch' && inputs.mode == 'daily-both' &&
        inputs.slot == 'both' && inputs.confirmation == '' &&
        github.actor == 'carloshuangspec' && github.triggering_actor == 'carloshuangspec'))
    permissions:
      contents: write
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      claimed: ${{ steps.claim.outputs.claimed }}
      day: ${{ steps.claim.outputs.day }}
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-python@v7
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - id: claim
        env:
          GH_TOKEN: ${{ github.token }}
          DELIVERY_DATE: ${{ inputs.delivery_date }}
        run: python src/daily_claim.py
```

The paired sender's complete new job gate is:

```yaml
  daily-both:
    needs: [validate-dispatch, claim-daily]
    if: >
      needs.validate-dispatch.result == 'success' &&
      needs.claim-daily.result == 'success' &&
      needs.claim-daily.outputs.claimed == 'true' &&
      vars.ENABLE_CN_DAILY == '1' && vars.ENABLE_SELF_DAILY == '1' &&
      github.repository == 'carloshuangspec/wechat-ldr-daily-push' &&
      github.ref == 'refs/heads/main' && github.run_attempt == '1' &&
      ((github.event_name == 'schedule' && github.event.schedule == '0 9 * * *') ||
       (github.event_name == 'workflow_dispatch' && inputs.mode == 'daily-both' &&
        inputs.slot == 'both' && inputs.confirmation == '' &&
        github.actor == 'carloshuangspec' && github.triggering_actor == 'carloshuangspec'))
    permissions:
      contents: read
```

Keep both Secrets only in its final sending step, retain its existing checkout/setup/tests, and pass:

```yaml
          DAILY_CLAIM_CREATED: ${{ needs.claim-daily.outputs.claimed }}
          DAILY_CLAIM_DATE: ${{ needs.claim-daily.outputs.day }}
          ENABLE_CN_DAILY: ${{ vars.ENABLE_CN_DAILY }}
          ENABLE_SELF_DAILY: ${{ vars.ENABLE_SELF_DAILY }}
          LIVE_DISPATCH_MODE: ${{ inputs.mode }}
          LIVE_DISPATCH_SLOT: ${{ inputs.slot }}
          LIVE_DISPATCH_DATE: ${{ inputs.delivery_date }}
```

Do not add `WECHAT_*` to the claim job or `GH_TOKEN` to the send job. Keep checkout's `persist-credentials: false`. The old schedule and Grok dispatch both use exactly this claim before the same paired sender, not two send jobs. Update `tests/test_stage_c.py`'s old `scheduled-both`/hard-coded job-count assertions and `tests/test_daily_workflow.py`'s fixed job-slicing tuple to reflect the new `claim-daily` plus renamed `daily-both` while retaining stage-specific single schedule tests. The claim job is not a message job, so exclude it from assertions that every job loads DeepSeek or `KNOWN_START_DATE`.

- [ ] **Step 4: Prove green and validate YAML.** Run full 146+ tests; use `git diff --check` and a local YAML parser (`ruby -e 'require "yaml"; YAML.load_file(ARGV[0])' .github/workflows/daily-push.yml`, if available) to catch syntax errors. Update README staging notes without claiming Grok is active.
- [ ] **Step 5: Commit and deploy staging.** Commit only code/tests/docs; inspect `git status`, verify remote `main` has not diverged, then push. If remote changes meanwhile, stop and reconcile rather than overwrite. Confirm workflow source/variables and use existing owner access to run `mode=preview,slot=both`; inspect only redacted logs. Do not invoke `daily-both` manually and do not enable Grok routine yet.

### Task 4: Prove Grok can dispatch a credential-free preview

**Files:** No code edits. Grok Bot and GitHub settings UI, only the named repository.

- [ ] **Step 1: Prepare scoped permission.** With Carlos's action-time confirmation, use GitHub UI to create a new fine-grained PAT for only `carloshuangspec/wechat-ldr-daily-push`, repository permission `Actions: write`, an expiry, and GitHub-required Metadata read. Carlos transfers its value directly into Grok Build's secure credential form; do not reveal it in chat, terminal or local files. Keep/verify the existing read-only monitor credential separately.
- [ ] **Step 2: Verify actual capability.** Ask Build to use the secure PAT to create `workflow_dispatch` on `main` with `mode=preview`, `slot=both` and no confirmation/date. Verify Build reports a real run URL, the run completes and `preview-both` has no WeChat credentials. If Grok cannot dispatch, stop here; keep the original schedule running.
- [ ] **Step 3: Prepare, do not enable live routine.** Configure the draft Grok routine for `Asia/Shanghai` 09:00 with `mode=daily-both`, `slot=both`, `delivery_date` computed from Shanghai today, `ref=main`; never auto-retry a live run. Confirm its status remains paused until Task 5. Ensure the existing 09:20 monitor can access read-only Actions runs, and prepare new criteria `workflow_dispatch/daily-both/claimed day/CN+SELF accepted`; do not report a mere dispatch as delivery.

### Task 5: Remove the old scheduler and enable only Grok

**Files:** Modify `.github/workflows/daily-push.yml`, `src/main.py`, `tests/test_daily_schedule.py`, `tests/test_daily_workflow.py`, `tests/test_stage_c.py`, `tests/test_paired_delivery.py`, `README.md`.

- [ ] **Step 1: Write failing post-cutover tests.** Assert the workflow has no `schedule:`/`scheduled-cn`/`scheduled-self`/old schedule-only preview clauses; `daily-both` permits only the owner/main/first-attempt dispatch via claimed day; Python rejects any `GITHUB_EVENT_NAME=schedule` live context; manual live-self/live-cn and preview continue to pass. Replace the old schedule-assuming tests with explicit post-cutover policy, not deleted coverage. Example:

```python
self.assertNotIn("  schedule:\n", workflow)
self.assertNotIn("  scheduled-cn:\n", workflow)
self.assertNotIn("  scheduled-self:\n", workflow)
self.assertIn("  daily-both:\n", workflow)
with patch.dict(os.environ, {**PAIRED_ENV, "GITHUB_EVENT_NAME": "schedule"}, clear=True):
    with self.assertRaises(main.ConfigError):
        main.validate_send_context("live", "cn")
```

- [ ] **Step 2: Prove red.** Run full suite; expect the new no-schedule assertions to fail while the staging schedule still exists.
- [ ] **Step 3: Cut over code.** Remove `"on".schedule`, schedule-only preview `if` arms and `scheduled-cn` / `scheduled-self` jobs. Make `validate-dispatch` reject every event other than `workflow_dispatch` and make `claim-daily`/`daily-both` require only `inputs.mode == 'daily-both'` with the strict owner/main/attempt/date checks. Remove `src/main.py`'s `schedule` live branch; keep claimed dispatch and manual single-user branches. Rewrite README's schedule and current-status sections to say Grok controls 09:00 and GitHub runs the sender; the former daily flags remain exact dual-on prerequisites, not independent single-person schedules.

```bash
if [ "$REQUEST_EVENT" != workflow_dispatch ]; then
  echo "::error::Unsupported workflow event."
  exit 1
fi
```

```yaml
"on":
  workflow_dispatch:
    inputs:
      mode:
        description: "preview / live-self / live-cn / daily-both"
        required: true
        default: preview
        type: choice
        options:
          - preview
          - live-self
          - live-cn
          - daily-both
      slot:
        description: "Preview slot; daily-both requires both"
        required: true
        default: cn
        type: choice
        options:
          - cn
          - us
          - both
      confirmation:
        description: "Single-recipient manual tests only"
        required: false
        default: ""
        type: string
      delivery_date:
        description: "Shanghai day YYYY-MM-DD; daily-both only"
        required: false
        default: ""
        type: string
```

Delete the schedule half of each paired job `if` expression, retaining the dispatch half with the exact owner/main/attempt/flags and claimed-output checks. In `src/main.py`, remove the entire `if os.getenv("GITHUB_EVENT_NAME") == "schedule": ... return` block; the `workflow_dispatch` paired branch from Task 2 then becomes the only automatic paired live route. In `tests/test_stage_c.py`, replace fixed counts tied to eight old message jobs with explicit assertions on the three preview, two manual, one claim and one paired job; in `tests/test_daily_workflow.py`, slice only those new jobs and assert the claim has neither DeepSeek nor WeChat Secrets.
- [ ] **Step 4: Prove green and deploy.** Run all tests, inspect YAML/diff, commit, check remote branch fast-forward, push. Verify remote `main` has no schedule entry and still accepts preview dispatch. Read-only inspect all old SHA schedule runs that are queued/in progress; do not enable Grok until those finish. If the old version sent today, wait until the next Shanghai date. The day claim, if already created, is never deleted as part of cutover.
- [ ] **Step 5: Update and activate Grok.** With action-time confirmation, set the 09:20 read-only monitor to inspect the new dispatch route, exact day claim and both acceptance markers. Prove monitor access still works. Activate the paused 09:00 Grok sender routine and verify its schedule/time zone and that no other automatic sender remains. Do not manually trigger live to test activation.

### Task 6: First daily run and recipient receipt

**Files:** No code edits unless the verified first run reveals a bug.

- [ ] **Step 1: Wait for the first 09:00 Shanghai routine.** Read Grok run history, GitHub workflow run ID and date claim; distinguish scheduled trigger, job start, each WeChat API acceptance and actual phone receipt. Grok may be late or fail, so do not promise minute-exact arrival.
- [ ] **Step 2: Resolve safely.** For absence/failure/partial delivery, report which stage failed and preserve the claim. Never retry automatically or remove the date ref; ask Carlos to check the two phones before any one-off recovery. If both steps accepted, ask Carlos to confirm both phones show the same English line, countdown and dates.
- [ ] **Step 3: Close out only on evidence.** Report remote SHA, Grok routine status, old scheduler absence, monitor behavior, a single date marker and both phone receipts. Until the first daily routine and both phones are confirmed, report setup as staged or activated-but-unverified, not complete.
