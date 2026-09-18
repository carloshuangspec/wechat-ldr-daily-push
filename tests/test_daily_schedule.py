from __future__ import annotations

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
import wechat  # noqa: E402


BASE_SCHEDULE = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "schedule",
    "GITHUB_EVENT_SCHEDULE": "0 9 * * *",
    "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_RUN_ATTEMPT": "1",
}


class DailyScheduleTests(unittest.TestCase):
    def test_both_recipients_have_separate_nine_am_shanghai_schedule_gates(self) -> None:
        with patch.dict(
            os.environ,
            {
                **BASE_SCHEDULE,
                "PUSH_SLOT": "cn",
                "LIVE_RECIPIENT": "cn",
                "ENABLE_CN_DAILY": "1",
            },
            clear=True,
        ):
            main.validate_send_context("live", "cn")
        with patch.dict(
            os.environ,
            {
                **BASE_SCHEDULE,
                "PUSH_SLOT": "us",
                "LIVE_RECIPIENT": "self",
                "ENABLE_SELF_DAILY": "1",
            },
            clear=True,
        ):
            main.validate_send_context("live", "us")

    def test_self_daily_rejects_disabled_flag_wrong_schedule_and_rerun(self) -> None:
        valid = {
            **BASE_SCHEDULE,
            "PUSH_SLOT": "us",
            "LIVE_RECIPIENT": "self",
            "ENABLE_SELF_DAILY": "1",
        }
        for key, value in (
            ("ENABLE_SELF_DAILY", "0"),
            ("GITHUB_EVENT_SCHEDULE", "7 8 * * *"),
            ("GITHUB_RUN_ATTEMPT", "2"),
            ("LIVE_RECIPIENT", "cn"),
        ):
            with self.subTest(key=key, value=value):
                with patch.dict(os.environ, {**valid, key: value}, clear=True):
                    with self.assertRaises(main.ConfigError):
                        main.validate_send_context("live", "us")

    def test_scheduled_self_sends_only_to_self_openid(self) -> None:
        env = {
            **BASE_SCHEDULE,
            "SEND_MODE": "live",
            "PUSH_SLOT": "us",
            "LIVE_RECIPIENT": "self",
            "ENABLE_SELF_DAILY": "1",
            "WECHAT_APP_ID": "TEST_APP",
            "WECHAT_APP_SECRET": "TEST_SECRET",
            "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE",
            "WECHAT_OPENID_SELF": "TEST_SELF",
            "WECHAT_OPENID_CN": "TEST_CN",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(
                main,
                "build_payload_fields",
                return_value={"meet_days": "in 95 days | Hello", "love_line": "Hello"},
            ),
            patch.object(
                main,
                "send_template",
                return_value={"errcode": 0, "msgid": "123"},
            ) as send,
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 0)
        self.assertEqual(send.call_args.kwargs["openid"], "TEST_SELF")

    def test_scheduled_self_does_not_fall_back_to_cn_openid(self) -> None:
        env = {
            **BASE_SCHEDULE,
            "SEND_MODE": "live",
            "PUSH_SLOT": "us",
            "LIVE_RECIPIENT": "self",
            "ENABLE_SELF_DAILY": "1",
            "WECHAT_APP_ID": "TEST_APP",
            "WECHAT_APP_SECRET": "TEST_SECRET",
            "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE",
            "WECHAT_OPENID_CN": "TEST_CN",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "build_payload_fields") as build,
            patch.object(main, "send_template") as send,
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 2)
        build.assert_not_called()
        send.assert_not_called()

    def test_workflow_one_shanghai_schedule_and_isolated_self_job(self) -> None:
        workflow = (ROOT / ".github/workflows/daily-push.yml").read_text(encoding="utf-8")
        schedule = workflow.split('  schedule:\n', 1)[1].split('  workflow_dispatch:', 1)[0]
        self.assertEqual(schedule.count('cron: "0 9 * * *"'), 0)
        self.assertIn('timezone: "Asia/Shanghai"', schedule)
        self.assertNotIn('America/Detroit', schedule)
        self.assertIn("  scheduled-self:", workflow)
        job = workflow.split("  scheduled-self:\n", 1)[1].split("  claim-daily:\n", 1)[0]
        for fragment in (
            "github.event_name == 'schedule'",
            "github.event.schedule == '0 9 * * *'",
            "vars.ENABLE_SELF_DAILY == '1'",
            "GITHUB_EVENT_SCHEDULE: ${{ github.event.schedule }}",
            "ENABLE_SELF_DAILY: ${{ vars.ENABLE_SELF_DAILY }}",
            "PUSH_SLOT: us",
            "LIVE_RECIPIENT: self",
            "WECHAT_OPENID_SELF: ${{ secrets.WECHAT_OPENID_SELF }}",
        ):
            self.assertIn(fragment, job)
        self.assertNotIn("WECHAT_OPENID_CN:", job)
        self.assertNotIn("DAILY_MESSAGE_CONFIG:", job)

    def test_recipient_greeting_uses_own_local_time(self) -> None:
        for hour, greeting in (
            ("09:00", "Good morning, love!"),
            ("15:00", "Afternoon, love!"),
            ("21:00", "Good evening, love!"),
        ):
            with (
                self.subTest(hour=hour),
                patch.dict(
                    os.environ,
                    {
                        "PUSH_SLOT": "us",
                        "LOVE_START_DATE": "2026-07-08",
                        "NEXT_MEET_DATE": "2026-12-20",
                    },
                    clear=True,
                ),
                patch.object(main, "local_today", return_value=date(2026, 9, 16)),
                patch.object(main, "local_now_str", side_effect=[hour, "09:00"]),
                patch.object(main, "brief_weather", return_value="Clear 20°C"),
                patch.object(main, "generate_love_line", return_value="I ache for you."),
            ):
                fields = main.build_payload_fields()
            self.assertEqual(fields["greeting"], greeting)
            self.assertEqual(fields["time_a"], hour)
            self.assertEqual(fields["time_b"], "09:00")
            self.assertEqual(wechat.build_template_data(fields)["greeting"]["value"], greeting)


if __name__ == "__main__":
    unittest.main()
