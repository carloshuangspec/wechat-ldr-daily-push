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

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import main  # noqa: E402
import wechat  # noqa: E402


BASE_ENV = {
    "PUSH_SLOT": "cn",
    "LOVE_START_DATE": "2026-07-08",
    "NEXT_MEET_DATE": "2026-12-20",
}


class DailyIntegrationTests(unittest.TestCase):
    def test_visible_meeting_field_carries_full_deepseek_line(self) -> None:
        with (
            patch.dict(os.environ, {**BASE_ENV, "PUSH_SLOT": "us"}, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="I ache for you."),
        ):
            fields = main.build_payload_fields()
        self.assertEqual(fields["meet_days"], "in 95 days")
        self.assertEqual(
            wechat.build_template_data(fields)["meet_days"]["value"],
            "in 95 days",
        )
        self.assertEqual(fields["love_line"], "I ache for you.")
        self.assertTrue(fields["greeting"].startswith("Known: ≈"))
        self.assertNotIn("|", fields["meet_days"])

    def test_meeting_field_rejects_truncation_of_emotional_line(self) -> None:
        with self.assertRaises(ValueError):
            wechat.build_template_data({"meet_days": "in 95 days" + "X" * 65})

    def test_exact_cn_line_bypasses_provider_and_survives_rendering(self) -> None:
        env = {
            **BASE_ENV,
            "DAILY_MESSAGE_CONFIG": json.dumps(
                {"date": "2026-09-16", "theme": "ordinary days", "exact": "My favorite day"}
            ),
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)) as today,
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line") as generate,
            redirect_stderr(StringIO()),
        ):
            fields = main.build_payload_fields()
        generate.assert_not_called()
        today.assert_called_once_with("Asia/Shanghai")
        self.assertEqual(fields["love_line"], "My favorite day")
        self.assertEqual(fields["greeting"], "Known: ≈2572 days")
        self.assertEqual(fields["meet_days"], "in 95 days")
        self.assertEqual(
            wechat.build_template_data(fields)["love_line"]["value"], fields["love_line"]
        )

    def test_matching_theme_guides_one_api_call(self) -> None:
        env = {**BASE_ENV, "DAILY_MESSAGE_CONFIG": '{"date":"2026-09-16","theme":"ordinary days"}'}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Here with you") as generate,
            redirect_stderr(StringIO()),
        ):
            fields = main.build_payload_fields()
        generate.assert_called_once_with(
            theme="ordinary days",
            time_a="08:00",
            time_b="08:00",
            weather_a="Clear 20°C",
            weather_b="Clear 20°C",
        )
        self.assertEqual(fields["love_line"], "Here with you")
        self.assertTrue(fields["greeting"].startswith("Known: ≈"))

    def test_stale_cn_config_uses_default_prompt(self) -> None:
        env = {**BASE_ENV, "DAILY_MESSAGE_CONFIG": '{"date":"2026-09-15","exact":"Yesterday"}'}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Here with you") as generate,
            redirect_stderr(StringIO()),
        ):
            main.build_payload_fields()
        generate.assert_called_once_with(
            theme=None,
            time_a="08:00",
            time_b="08:00",
            weather_a="Clear 20°C",
            weather_b="Clear 20°C",
        )

    def test_us_ignores_even_malformed_cn_config(self) -> None:
        env = {**BASE_ENV, "PUSH_SLOT": "us", "DAILY_MESSAGE_CONFIG": "{invalid"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)) as today,
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Here with you") as generate,
            redirect_stderr(StringIO()),
        ):
            main.build_payload_fields()
        today.assert_called_once_with("America/Detroit")
        generate.assert_called_once_with(
            theme=None,
            time_a="08:00",
            time_b="08:00",
            weather_a="Clear 20°C",
            weather_b="Clear 20°C",
        )

    def test_bad_cn_config_fails_before_weather_or_provider(self) -> None:
        with (
            patch.dict(os.environ, {**BASE_ENV, "DAILY_MESSAGE_CONFIG": "{invalid"}, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "brief_weather") as weather,
            patch.object(main, "generate_love_line") as generate,
        ):
            with self.assertRaises(ValueError):
                main.build_payload_fields()
        weather.assert_not_called()
        generate.assert_not_called()

    def test_template_rejects_long_love_line_without_ellipsis(self) -> None:
        with self.assertRaises(ValueError):
            wechat.build_template_data({"love_line": "X" * 65})

    def test_render_failure_cannot_send_or_leak_line(self) -> None:
        env = {
            **BASE_ENV,
            "SEND_MODE": "live",
            "LIVE_RECIPIENT": "cn",
            "LIVE_CONFIRMATION": "SEND_CN_ONCE",
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_ACTOR": "carloshuangspec",
            "GITHUB_TRIGGERING_ACTOR": "carloshuangspec",
            "GITHUB_RUN_ATTEMPT": "1",
            "WECHAT_APP_ID": "TEST_APP_ID",
            "WECHAT_APP_SECRET": "TEST_SECRET",
            "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE",
            "WECHAT_OPENID_CN": "TEST_OPENID",
        }
        stderr = StringIO()
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "build_payload_fields", return_value={"love_line": "X" * 65}),
            patch.object(main, "send_template") as send,
            redirect_stderr(stderr),
        ):
            self.assertEqual(main.main(), 1)
        send.assert_not_called()
        self.assertNotIn("X" * 65, stderr.getvalue())

    def test_preview_reports_only_fixed_metadata_not_theme(self) -> None:
        env = {
            **BASE_ENV,
            "DAILY_MESSAGE_CONFIG": '{"date":"2026-09-16","theme":"private-theme-marker"}',
        }
        stdout = StringIO()
        stderr = StringIO()
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Here with you"),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(main.main(), 0)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["meta"]["deepseek_key_set"])
        self.assertNotIn("private-theme-marker", stdout.getvalue() + stderr.getvalue())
        self.assertIn("override_status=active", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
