# WeChat daily push: self-test and approximate acquaintance count

Date: 2026-09-16

## Goal and boundaries

Keep the existing English WeChat test-account template. For a first live test, send the same current-format message separately to Carlos's own account and his girlfriend's account. Only after checking the API response and both phones should we enable the girlfriend's daily scheduled delivery. The self-test does not authorize daily messages to Carlos. Scheduled US and CN previews remain available.

Do not read or print Secret values. The existing `WECHAT_OPENID_CN` remains the girlfriend's recipient; the newly saved `WECHAT_OPENID_SELF` is Carlos's. Never swap or fall back between them. The QR follow action is done by each recipient in WeChat, not by the bot.

## Chosen presentation

`2019-09-02` is an approximate counting anchor, not a verified day when the couple met. Continue the project's inclusive day convention, so on 2026-09-16 the value is `≈2572 days`. Keep the confirmed relationship restart `2026-07-08` in the separate `Together` field. All ordinary message words remain English; allow `≈` only in the acquaintance line and `°` in temperatures.

Carlos has now explicitly confirmed all configured dates, including the next meeting on `2026-12-20`. Preserve the existing real `Next meeting` countdown from `NEXT_MEET_DATE`; do not replace it with `TBD`. Keep that date separate from both the approximate acquaintance anchor and the relationship restart.

Avoid changing the test-account template or its ID for this first test. Use the existing `{{love_line.DATA}}` position for two lines: `Known: ≈N days` followed by the generated English love line. Increase that field's truncation limit enough for both lines. If the phone renderer flattens the newline, the first test can still reveal it; a separate `known_days` template field can be a later, explicitly chosen improvement. The existing `Weather` attribution remains untouched. A non-sensitive `KNOWN_START_DATE` configuration defaults to `2019-09-02` and must reject an invalid date.

## Send flow and safety

Keep preview as the default. Add an independent owner-only manual `live-self` path for `PUSH_SLOT=us`, with its own exact confirmation string, that receives only `WECHAT_OPENID_SELF` and never `WECHAT_OPENID_CN`. Preserve the existing owner-only manual `live-cn` path for `PUSH_SLOT=cn` and its own confirmation string; it sees only `WECHAT_OPENID_CN`. Check the recipient role, slot, repository, branch, actor, event type and first run attempt in both the workflow and Python before fetching weather or accessing the WeChat API. A new workflow dispatch is not cryptographically once-only, so avoid retries without checking the recipient's phone.

First run tests and a CN/US preview on the final pushed commit. Inspect the message text, including the approximate count and the confirmed next-meeting countdown, without logging recipient IDs or API credentials. Trigger one self manual send, check the redacted API result, then trigger one CN manual send under the user's current authorization and check its redacted result. Ask Carlos to verify both phones received the message. An accepted API result or green job alone is not proof of delivery. Stop and diagnose if either step fails; do not automatically re-send.

The two existing scheduled jobs stay dry-run during the first live tests. Prepare a separately gated CN schedule that loads only `WECHAT_OPENID_CN` while the explicit repository variable `ENABLE_CN_DAILY` remains absent/off; this preparation cannot send. Only after both phone receipts and content are confirmed may that variable be set to `1`. Its Python and workflow checks must recognize the exact CN schedule event and cron separately from the manual owner/confirmation gate; a scheduled event cannot reuse `workflow_dispatch` actor/confirmation assumptions. The US schedule stays preview-only; the user can separately request daily US sends later. Disable the CN gate immediately if output or delivery is wrong. Never expose credentials in errors or logs.

## Verification

Unit tests cover inclusive approximate counting, invalid acquaintance date, confirmed meeting date validation/countdown, exact English output with only `≈`/`°` exceptions, non-truncation of the two-line field, template field compatibility, default dry-run, recipient separation, missing Secret failures, rejected wrong modes/slots/actors/branches/events/re-runs, and schedule disabled by default. Validate the final workflow on GitHub, then distinguish preview success, WeChat API acceptance, and phone receipt in the handoff.
