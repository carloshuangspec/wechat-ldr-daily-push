"""Both daily recipients must receive one identical Shanghai-day snapshot."""

from __future__ import annotations

import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import main  # noqa: E402


PAIRED_ENV = {
    "SEND_MODE": "live",
    "PUSH_SLOT": "cn",
    "LIVE_RECIPIENT": "both",
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "schedule",
    "GITHUB_EVENT_SCHEDULE": "0 9 * * *",
    "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_RUN_ATTEMPT": "1",
    "ENABLE_CN_DAILY": "1",
    "ENABLE_SELF_DAILY": "1",
    "DAILY_CLAIM_CREATED": "true",
    "DAILY_CLAIM_DATE": "2026-09-17",
    "WECHAT_APP_ID": "TEST_APP",
    "WECHAT_APP_SECRET": "TEST_SECRET_NOT_FOR_LOGS",
    "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE_NOT_FOR_LOGS",
    "WECHAT_OPENID_CN": "TEST_CN_OPENID_NOT_FOR_LOGS",
    "WECHAT_OPENID_SELF": "TEST_SELF_OPENID_NOT_FOR_LOGS",
    "LOVE_START_DATE": "2026-07-08",
    "NEXT_MEET_DATE": "2026-12-20",
}

DISPATCH_ENV = {
    **PAIRED_ENV,
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_ACTOR": "carloshuangspec",
    "GITHUB_TRIGGERING_ACTOR": "carloshuangspec",
    "LIVE_DISPATCH_MODE": "daily-both",
    "LIVE_DISPATCH_SLOT": "both",
    "LIVE_DISPATCH_DATE": "2026-09-17",
}
DISPATCH_ENV.pop("GITHUB_EVENT_SCHEDULE")


class PairedDeliveryTests(unittest.TestCase):
    def test_workflow_routes_both_switches_to_only_one_paired_job(self) -> None:
        workflow = (ROOT / ".github/workflows/daily-push.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count('cron: "0 9 * * *"'), 1)
        self.assertIn("  claim-daily:\n", workflow)
        self.assertIn("  daily-both:\n", workflow)
        cn_job = workflow.split("  scheduled-cn:\n", 1)[1].split("  scheduled-self:\n", 1)[0]
        self_job = workflow.split("  scheduled-self:\n", 1)[1].split("  claim-daily:\n", 1)[0]
        claim_job = workflow.split("  claim-daily:\n", 1)[1].split("  daily-both:\n", 1)[0]
        both_job = workflow.split("  daily-both:\n", 1)[1]
        self.assertIn("vars.ENABLE_SELF_DAILY != '1'", cn_job)
        self.assertIn("vars.ENABLE_CN_DAILY != '1'", self_job)
        for role, job in (("CN", cn_job), ("SELF", self_job)):
            self.assertIn(f"ENABLE_{role}_DAILY: ${{{{ vars.ENABLE_{role}_DAILY }}}}", job)
        for fragment in (
            "github.event_name == 'schedule'",
            "github.event.schedule == '0 9 * * *'",
            "github.event_name == 'workflow_dispatch'",
            "inputs.mode == 'daily-both'",
            "inputs.slot == 'both'",
            "inputs.confirmation == ''",
            "github.actor == 'carloshuangspec'",
            "github.triggering_actor == 'carloshuangspec'",
            "vars.ENABLE_CN_DAILY == '1'",
            "vars.ENABLE_SELF_DAILY == '1'",
            "github.repository == 'carloshuangspec/wechat-ldr-daily-push'",
            "github.ref == 'refs/heads/main'",
            "github.run_attempt == '1'",
            "PUSH_SLOT: cn",
            "SEND_MODE: live",
            "LIVE_RECIPIENT: both",
            "ENABLE_CN_DAILY: ${{ vars.ENABLE_CN_DAILY }}",
            "ENABLE_SELF_DAILY: ${{ vars.ENABLE_SELF_DAILY }}",
            "DAILY_CLAIM_CREATED: ${{ needs.claim-daily.outputs.claimed }}",
            "DAILY_CLAIM_DATE: ${{ needs.claim-daily.outputs.day }}",
            "LIVE_DISPATCH_MODE: ${{ inputs.mode }}",
            "LIVE_DISPATCH_SLOT: ${{ inputs.slot }}",
            "LIVE_DISPATCH_DATE: ${{ inputs.delivery_date }}",
            "WECHAT_OPENID_CN: ${{ secrets.WECHAT_OPENID_CN }}",
            "WECHAT_OPENID_SELF: ${{ secrets.WECHAT_OPENID_SELF }}",
            "DAILY_MESSAGE_CONFIG: ${{ secrets.DAILY_MESSAGE_CONFIG }}",
            "python -m unittest discover -s tests -v",
        ):
            self.assertIn(fragment, both_job)
        self.assertIn("needs: [validate-dispatch, claim-daily]", both_job)
        self.assertIn("needs.claim-daily.result == 'success'", both_job)
        self.assertIn("needs.claim-daily.outputs.claimed == 'true'", both_job)
        self.assertIn("permissions:\n      contents: read", both_job)
        self.assertNotIn("GH_TOKEN:", both_job)
        self.assertNotIn("WECHAT_", claim_job)
        self.assertNotIn("DEEPSEEK_API_KEY", claim_job)
        self.assertNotIn("DAILY_MESSAGE_CONFIG", claim_job)

    def test_daily_both_dispatch_claim_is_isolated_and_precedes_only_paired_sender(self) -> None:
        workflow = (ROOT / ".github/workflows/daily-push.yml").read_text(encoding="utf-8")
        claim_job = workflow.split("  claim-daily:\n", 1)[1].split("  daily-both:\n", 1)[0]
        sender = workflow.split("  daily-both:\n", 1)[1]
        self.assertEqual(workflow.count("  daily-both:\n"), 1)
        self.assertLess(workflow.index("  claim-daily:\n"), workflow.index("  daily-both:\n"))
        for fragment in (
            "needs: validate-dispatch",
            "timeout-minutes: 5",
            "permissions:\n      contents: write",
            "outputs:",
            "claimed: ${{ steps.claim.outputs.claimed }}",
            "day: ${{ steps.claim.outputs.day }}",
            "id: claim",
            "GH_TOKEN: ${{ github.token }}",
            "DELIVERY_DATE: ${{ inputs.delivery_date }}",
            "run: pip install -r requirements.txt",
            "python src/daily_claim.py",
            "github.event.schedule == '0 9 * * *'",
            "inputs.mode == 'daily-both'",
            "inputs.slot == 'both'",
            "inputs.confirmation == ''",
            "github.run_attempt == '1'",
        ):
            self.assertIn(fragment, claim_job)
        self.assertNotIn("retry", claim_job.lower())
        self.assertNotIn("GH_TOKEN:", sender)

    def test_both_preview_is_one_credential_free_job(self) -> None:
        workflow = (ROOT / ".github/workflows/daily-push.yml").read_text(encoding="utf-8")
        cn_job = workflow.split("  preview-cn:\n", 1)[1].split("  preview-us:\n", 1)[0]
        us_job = workflow.split("  preview-us:\n", 1)[1].split("  preview-both:\n", 1)[0]
        both_job = workflow.split("  preview-both:\n", 1)[1].split("  live-self:\n", 1)[0]
        self.assertNotIn("inputs.slot == 'both'", cn_job + us_job)
        self.assertIn("inputs.slot == 'both'", both_job)
        self.assertIn("LIVE_RECIPIENT: both", both_job)
        self.assertIn("PUSH_SLOT: cn", both_job)
        self.assertIn("SEND_MODE: dry-run", both_job)
        self.assertIn("DAILY_MESSAGE_CONFIG: ${{ secrets.DAILY_MESSAGE_CONFIG }}", both_job)
        self.assertNotIn("WECHAT_APP_ID:", both_job)
        self.assertNotIn("WECHAT_APP_SECRET:", both_job)
        self.assertNotIn("WECHAT_OPENID_", both_job)

    def test_one_generated_snapshot_is_sent_unchanged_to_two_distinct_recipients(self) -> None:
        stdout, stderr = StringIO(), StringIO()
        with (
            patch.dict(os.environ, PAIRED_ENV, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 17)) as today,
            patch.object(main, "local_now_str", side_effect=["21:00", "09:00"]) as clock,
            patch.object(main, "brief_weather", side_effect=["Cloudy 20°C", "Fair 25°C"]) as weather,
            patch.object(main, "generate_love_line", return_value="Always, with you.") as line,
            patch.object(main, "send_template", return_value={"errcode": 0, "msgid": "123"}) as send,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(main.main(), 0)
        self.assertEqual(today.call_count, 3)
        today.assert_has_calls([unittest.mock.call("Asia/Shanghai")] * 3)
        self.assertEqual(clock.call_count, 2)
        self.assertEqual(weather.call_count, 2)
        line.assert_called_once_with(
            theme=None,
            time_a="21:00",
            time_b="09:00",
            weather_a="Cloudy 20°C",
            weather_b="Fair 25°C",
        )
        self.assertEqual(send.call_count, 2)
        first, second = [call.kwargs for call in send.call_args_list]
        self.assertEqual(
            {first["openid"], second["openid"]},
            {PAIRED_ENV["WECHAT_OPENID_CN"], PAIRED_ENV["WECHAT_OPENID_SELF"]},
        )
        self.assertIs(first["data"], second["data"])
        self.assertEqual(first["data"]["greeting"]["value"], "Known: ≈2573 days")
        self.assertEqual(first["data"]["love_days"]["value"], "72 days")
        self.assertEqual(first["data"]["meet_days"]["value"], "in 94 days")
        self.assertEqual(first["data"]["love_line"]["value"], "Always, with you.")
        self.assertNotIn("Known", first["data"]["love_line"]["value"])
        self.assertNotIn("|", first["data"]["meet_days"]["value"])
        for secret in ("WECHAT_APP_SECRET", "WECHAT_TEMPLATE_ID", "WECHAT_OPENID_CN", "WECHAT_OPENID_SELF"):
            self.assertNotIn(PAIRED_ENV[secret], stdout.getvalue() + stderr.getvalue())

    def test_any_invalid_paired_gate_stops_before_build_or_send(self) -> None:
        for name, value in (
            ("ENABLE_CN_DAILY", "0"),
            ("ENABLE_SELF_DAILY", ""),
            ("GITHUB_EVENT_NAME", "workflow_dispatch"),
            ("GITHUB_EVENT_SCHEDULE", "0 8 * * *"),
            ("GITHUB_REPOSITORY", "someone/fork"),
            ("GITHUB_REF", "refs/heads/other"),
            ("GITHUB_RUN_ATTEMPT", "2"),
            ("PUSH_SLOT", "us"),
            ("WECHAT_OPENID_CN", ""),
            ("WECHAT_OPENID_SELF", ""),
            ("WECHAT_OPENID_SELF", PAIRED_ENV["WECHAT_OPENID_CN"]),
        ):
            with (
                self.subTest(name=name, value=value),
                patch.dict(os.environ, {**PAIRED_ENV, name: value}, clear=True),
                patch.object(main, "local_today", return_value=date(2026, 9, 17)),
                patch.object(main, "build_payload_fields") as build,
                patch.object(main, "send_template") as send,
                redirect_stderr(StringIO()),
            ):
                self.assertEqual(main.main(), 2)
                build.assert_not_called()
                send.assert_not_called()

    def test_claimed_dispatch_accepts_only_the_exact_paired_context(self) -> None:
        with (
            patch.dict(os.environ, DISPATCH_ENV, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 17)),
        ):
            main.validate_send_context("live", "cn")

        for name, value in (
            ("LIVE_DISPATCH_MODE", "preview"),
            ("LIVE_DISPATCH_SLOT", "cn"),
            ("LIVE_DISPATCH_DATE", "2026-09-18"),
            ("GITHUB_ACTOR", "someone-else"),
            ("GITHUB_TRIGGERING_ACTOR", "someone-else"),
            ("GITHUB_REPOSITORY", "someone/fork"),
            ("GITHUB_REF", "refs/heads/other"),
            ("GITHUB_RUN_ATTEMPT", "2"),
            ("DAILY_CLAIM_CREATED", ""),
            ("DAILY_CLAIM_CREATED", " true "),
            ("DAILY_CLAIM_DATE", "2026-09-18"),
            ("DAILY_CLAIM_DATE", " 2026-09-17 "),
            ("ENABLE_CN_DAILY", "0"),
            ("ENABLE_CN_DAILY", " 1 "),
            ("ENABLE_SELF_DAILY", "0"),
            ("ENABLE_SELF_DAILY", " 1 "),
            ("LIVE_DISPATCH_MODE", " daily-both "),
            ("LIVE_DISPATCH_DATE", " 2026-09-17 "),
            ("PUSH_SLOT", "us"),
        ):
            with (
                self.subTest(name=name, value=value),
                patch.dict(os.environ, {**DISPATCH_ENV, name: value}, clear=True),
                patch.object(main, "local_today", return_value=date(2026, 9, 17)),
                patch.object(main, "build_payload_fields") as build,
                patch.object(main, "send_template") as send,
                redirect_stderr(StringIO()),
            ):
                self.assertEqual(main.main(), 2)
                build.assert_not_called()
                send.assert_not_called()

    def test_scheduled_both_requires_a_current_claim(self) -> None:
        for name, value in (
            ("DAILY_CLAIM_CREATED", ""),
            ("DAILY_CLAIM_DATE", "2026-09-18"),
        ):
            with (
                self.subTest(name=name, value=value),
                patch.dict(os.environ, {**PAIRED_ENV, name: value}, clear=True),
                patch.object(main, "local_today", return_value=date(2026, 9, 17)),
            ):
                with self.assertRaises(main.ConfigError):
                    main.validate_send_context("live", "cn")

    def test_paired_payload_uses_shanghai_day_even_if_city_b_timezone_changes(self) -> None:
        with (
            patch.dict(os.environ, {**PAIRED_ENV, "CITY_B_TZ": "America/Detroit"}, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 17)) as today,
            patch.object(main, "local_now_str", side_effect=["21:00", "09:00"]),
            patch.object(main, "brief_weather", return_value="Fair 20°C"),
            patch.object(main, "generate_love_line", return_value="With you, always"),
        ):
            main.build_payload_fields()
        today.assert_called_once_with("Asia/Shanghai")

    def test_paired_payload_rejects_wrong_claim_before_weather_or_line_generation(self) -> None:
        with (
            patch.dict(os.environ, {**PAIRED_ENV, "DAILY_CLAIM_DATE": "2026-09-18"}, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 17)),
            patch.object(main, "brief_weather") as weather,
            patch.object(main, "generate_love_line") as generate,
        ):
            with self.assertRaises(main.ConfigError):
                main.build_payload_fields()
        weather.assert_not_called()
        generate.assert_not_called()

    def test_paired_live_stops_when_shanghai_day_changes_before_send(self) -> None:
        with (
            patch.dict(os.environ, PAIRED_ENV, clear=True),
            patch.object(main, "local_today", side_effect=[date(2026, 9, 17), date(2026, 9, 18)]),
            patch.object(main, "build_payload_fields", return_value={"meet_days": "today", "love_line": "Hello", "greeting": "Known: ≈1 days"}),
            patch.object(main, "send_template") as send,
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 2)
        send.assert_not_called()

    def test_single_schedule_cannot_send_when_other_daily_switch_is_on(self) -> None:
        for recipient, slot, extra in (
            ("cn", "cn", {"ENABLE_SELF_DAILY": "1"}),
            ("self", "us", {"ENABLE_CN_DAILY": "1"}),
        ):
            with (
                self.subTest(recipient=recipient),
                patch.dict(
                    os.environ,
                    {**PAIRED_ENV, "LIVE_RECIPIENT": recipient, "PUSH_SLOT": slot, **extra},
                    clear=True,
                ),
                patch.object(main, "local_today", return_value=date(2026, 9, 17)),
            ):
                with self.assertRaises(main.ConfigError):
                    main.validate_send_context("live", slot)

    def test_partial_failure_reports_first_acceptance_without_retry(self) -> None:
        stdout, stderr = StringIO(), StringIO()
        with (
            patch.dict(os.environ, PAIRED_ENV, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 17)),
            patch.object(main, "build_payload_fields", return_value={"meet_days": "today", "love_line": "Hello", "greeting": "Known: ≈1 days"}),
            patch.object(main, "send_template", side_effect=[{"errcode": 0, "msgid": "123"}, RuntimeError("TEST_SECRET_NOT_FOR_LOGS")]) as send,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(main.main(), 1)
        self.assertEqual(send.call_count, 2)
        self.assertIn('"recipient": "cn"', stdout.getvalue())
        self.assertNotIn('"recipient": "self"', stdout.getvalue())
        self.assertIn("recipient=self", stderr.getvalue())
        self.assertNotIn("TEST_SECRET_NOT_FOR_LOGS", stdout.getvalue() + stderr.getvalue())

    def test_shanghai_day_exact_override_reaches_both_without_api(self) -> None:
        env = {
            **PAIRED_ENV,
            "DAILY_MESSAGE_CONFIG": json.dumps(
                {"date": "2026-09-17", "exact": "One page at a time"}
            ),
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 17)),
            patch.object(main, "local_now_str", side_effect=["21:00", "09:00"]),
            patch.object(main, "brief_weather", return_value="Fair 20°C"),
            patch.object(main, "generate_love_line") as generate,
            patch.object(main, "send_template", return_value={"errcode": 0, "msgid": "123"}) as send,
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 0)
        generate.assert_not_called()
        self.assertEqual(send.call_count, 2)
        for call in send.call_args_list:
            self.assertEqual(
                call.kwargs["data"]["meet_days"]["value"],
                "in 94 days",
            )
            self.assertEqual(
                call.kwargs["data"]["love_line"]["value"],
                "One page at a time",
            )
            self.assertTrue(
                call.kwargs["data"]["greeting"]["value"].startswith("Known: ≈")
            )

    def test_paired_preview_has_known_greeting_without_wechat_credentials(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"SEND_MODE": "dry-run", "PUSH_SLOT": "cn", "LIVE_RECIPIENT": "both", "KNOWN_START_DATE": "2019-09-02", "LOVE_START_DATE": "2026-07-08", "NEXT_MEET_DATE": "2026-12-20"},
                clear=True,
            ),
            patch.object(main, "local_today", return_value=date(2026, 9, 17)),
            patch.object(main, "local_now_str", side_effect=["21:00", "09:00"]),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="With you, always"),
            patch.object(main, "send_template") as send,
            redirect_stdout(StringIO()) as stdout,
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 0)
        send.assert_not_called()
        self.assertIn('"greeting": {', stdout.getvalue())
        self.assertIn('"value": "Known: ≈2573 days"', stdout.getvalue())
        self.assertIn('"value": "With you, always"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
