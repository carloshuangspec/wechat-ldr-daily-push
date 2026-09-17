from __future__ import annotations

import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import requests

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import dates  # noqa: E402
import main  # noqa: E402
import weather  # noqa: E402
import wechat  # noqa: E402


LIVE_GITHUB_ENV = {
    "LIVE_RECIPIENT": "cn",
    "LIVE_CONFIRMATION": "SEND_CN_ONCE",
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_ACTOR": "carloshuangspec",
    "GITHUB_TRIGGERING_ACTOR": "carloshuangspec",
    "GITHUB_RUN_ATTEMPT": "1",
}

SCHEDULED_CN_ENV = {
    "SEND_MODE": "live",
    "PUSH_SLOT": "cn",
    "LIVE_RECIPIENT": "cn",
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "schedule",
    "GITHUB_EVENT_SCHEDULE": "0 9 * * *",
    "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_RUN_ATTEMPT": "1",
    "ENABLE_CN_DAILY": "1",
    "WECHAT_APP_ID": "TEST_APP_ID",
    "WECHAT_APP_SECRET": "TEST_SECRET_DO_NOT_LOG",
    "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE_DO_NOT_LOG",
    "WECHAT_OPENID_CN": "TEST_CN_OPENID_DO_NOT_LOG",
}

TEST_FIELDS = {
    "meet_days": "in 95 days | Hello",
    "love_line": "Known: ≈1 days\nHello",
}


class SendModeTests(unittest.TestCase):
    def test_default_is_dry_run_even_when_legacy_dry_run_is_zero(self) -> None:
        with patch.dict(os.environ, {"DRY_RUN": "0"}, clear=True):
            self.assertEqual(main.resolve_send_mode(), "dry-run")

    def test_default_mode_never_calls_send(self) -> None:
        stdout = StringIO()
        with (
            patch.dict(
                os.environ,
                {
                    "DRY_RUN": "0",
                    "PUSH_SLOT": "cn",
                    "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE_ID_DO_NOT_LOG",
                    "WECHAT_OPENID_CN": "TEST_OPENID_DO_NOT_LOG",
                },
                clear=True,
            ),
            patch.object(main, "build_payload_fields", return_value=TEST_FIELDS),
            patch.object(main, "send_template") as send,
            redirect_stdout(stdout),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 0)
            send.assert_not_called()
            self.assertNotIn("TEST_TEMPLATE_ID_DO_NOT_LOG", stdout.getvalue())
            self.assertNotIn("TEST_OPENID_DO_NOT_LOG", stdout.getvalue())
            self.assertFalse(json.loads(stdout.getvalue())["meta"]["deepseek_key_set"])

    def test_unknown_mode_stops_before_payload_build(self) -> None:
        for mode in ("unexpected", "live-cn", "0", "1", "true", "false"):
            with (
                self.subTest(mode=mode),
                patch.dict(
                    os.environ,
                    {"SEND_MODE": mode, "PUSH_SLOT": "cn"},
                    clear=True,
                ),
                patch.object(main, "build_payload_fields") as build,
            ):
                self.assertEqual(main.main(), 2)
                build.assert_not_called()

    def test_live_cn_requires_exact_confirmation_and_cn_slot(self) -> None:
        with patch.dict(os.environ, LIVE_GITHUB_ENV, clear=True):
            main.validate_send_context("live", "cn")
            with self.assertRaises(main.ConfigError):
                main.validate_send_context("live", "us")

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(main.ConfigError):
                main.validate_send_context("live", "cn")

    def test_live_self_allows_owner_first_attempt_us_dispatch(self) -> None:
        with patch.dict(
            os.environ,
            {
                **LIVE_GITHUB_ENV,
                "LIVE_RECIPIENT": "self",
                "LIVE_CONFIRMATION": "SEND_SELF_ONCE",
            },
            clear=True,
        ):
            main.validate_send_context("live", "us")

    def test_local_live_cn_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"LIVE_RECIPIENT": "cn", "LIVE_CONFIRMATION": "SEND_CN_ONCE"},
            clear=True,
        ):
            with self.assertRaises(main.ConfigError):
                main.validate_send_context("live", "cn")

    def test_actions_schedule_cannot_become_live_cn(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LIVE_RECIPIENT": "cn",
                "LIVE_CONFIRMATION": "SEND_CN_ONCE",
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "schedule",
                "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_ACTOR": "carloshuangspec",
                "GITHUB_TRIGGERING_ACTOR": "carloshuangspec",
                "GITHUB_RUN_ATTEMPT": "1",
            },
            clear=True,
        ):
            with self.assertRaises(main.ConfigError):
                main.validate_send_context("live", "cn")

    def test_scheduled_cn_live_sends_without_manual_confirmation(self) -> None:
        stdout = StringIO()
        with (
            patch.dict(os.environ, SCHEDULED_CN_ENV, clear=True),
            patch.object(main, "build_payload_fields", return_value=TEST_FIELDS) as build,
            patch.object(
                main, "send_template", return_value={"errcode": 0, "msgid": "123"}
            ) as send,
            redirect_stdout(stdout),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 0)
            build.assert_called_once_with()
            self.assertEqual(
                send.call_args.kwargs["openid"], SCHEDULED_CN_ENV["WECHAT_OPENID_CN"]
            )
            self.assertNotIn(SCHEDULED_CN_ENV["WECHAT_OPENID_CN"], stdout.getvalue())

    def test_scheduled_cn_rejects_missing_or_inexact_flag_before_weather(self) -> None:
        for flag in (None, "", "0", "true", " 1 ", "2"):
            with self.subTest(flag=flag):
                env = {**SCHEDULED_CN_ENV, "LIVE_CONFIRMATION": "SEND_CN_ONCE"}
                if flag is None:
                    del env["ENABLE_CN_DAILY"]
                else:
                    env["ENABLE_CN_DAILY"] = flag
                with (
                    patch.dict(os.environ, env, clear=True),
                    patch.object(main, "brief_weather") as weather_call,
                    patch.object(main, "build_payload_fields") as build,
                    patch.object(main, "send_template") as send,
                    redirect_stderr(StringIO()),
                ):
                    self.assertEqual(main.main(), 2)
                    weather_call.assert_not_called()
                    build.assert_not_called()
                    send.assert_not_called()

    def test_scheduled_cn_rejects_wrong_context_before_weather_or_send(self) -> None:
        invalid = {
            "wrong event": ("GITHUB_EVENT_NAME", "workflow_dispatch"),
            "missing cron": ("GITHUB_EVENT_SCHEDULE", ""),
            "US cron": ("GITHUB_EVENT_SCHEDULE", "13 8 * * *"),
            "different cron": ("GITHUB_EVENT_SCHEDULE", "8 8 * * *"),
            "wrong role": ("LIVE_RECIPIENT", "self"),
            "wrong slot": ("PUSH_SLOT", "us"),
            "padded slot": ("PUSH_SLOT", " cn"),
            "not Actions": ("GITHUB_ACTIONS", "false"),
            "non-exact Actions": ("GITHUB_ACTIONS", "TRUE"),
            "padded Actions": ("GITHUB_ACTIONS", "true "),
            "wrong repository": ("GITHUB_REPOSITORY", "someone/fork"),
            "wrong ref": ("GITHUB_REF", "refs/heads/feature"),
            "rerun": ("GITHUB_RUN_ATTEMPT", "2"),
        }
        for case, (name, value) in invalid.items():
            with (
                self.subTest(case=case),
                patch.dict(os.environ, {**SCHEDULED_CN_ENV, name: value}, clear=True),
                patch.object(main, "brief_weather") as weather_call,
                patch.object(main, "build_payload_fields") as build,
                patch.object(main, "send_template") as send,
                redirect_stderr(StringIO()),
            ):
                self.assertEqual(main.main(), 2)
                weather_call.assert_not_called()
                build.assert_not_called()
                send.assert_not_called()

    def test_manual_cn_confirmation_is_not_replaced_by_daily_flag(self) -> None:
        env = {
            **SCHEDULED_CN_ENV,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "LIVE_CONFIRMATION": "",
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

    def test_each_live_gate_field_stops_main_before_payload_or_send(self) -> None:
        valid_env = {
            "SEND_MODE": "live",
            "PUSH_SLOT": "cn",
            **LIVE_GITHUB_ENV,
            "WECHAT_APP_ID": "TEST_APP_ID",
            "WECHAT_APP_SECRET": "TEST_SECRET",
            "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE",
            "WECHAT_OPENID_CN": "TEST_OPENID",
        }
        invalid_values = {
            "LIVE_CONFIRMATION": "wrong",
            "GITHUB_ACTIONS": "false",
            "GITHUB_EVENT_NAME": "schedule",
            "GITHUB_REPOSITORY": "someone/fork",
            "GITHUB_REF": "refs/heads/feature",
            "GITHUB_ACTOR": "someone-else",
            "GITHUB_TRIGGERING_ACTOR": "someone-else",
            "GITHUB_RUN_ATTEMPT": "2",
        }
        for name, bad_value in invalid_values.items():
            with (
                self.subTest(name=name),
                patch.dict(
                    os.environ,
                    {**valid_env, name: bad_value},
                    clear=True,
                ),
                patch.object(main, "build_payload_fields") as build,
                patch.object(main, "send_template") as send,
                redirect_stderr(StringIO()),
            ):
                self.assertEqual(main.main(), 2)
                build.assert_not_called()
                send.assert_not_called()

    def test_invalid_live_self_context_stops_before_weather_build_or_send(self) -> None:
        valid_env = {
            "SEND_MODE": "live",
            "PUSH_SLOT": "us",
            **LIVE_GITHUB_ENV,
            "LIVE_RECIPIENT": "self",
            "LIVE_CONFIRMATION": "SEND_SELF_ONCE",
            "WECHAT_APP_ID": "TEST_APP_ID",
            "WECHAT_APP_SECRET": "TEST_SECRET",
            "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE",
            "WECHAT_OPENID_SELF": "TEST_SELF_OPENID",
            "WECHAT_OPENID_CN": "TEST_CN_OPENID_DO_NOT_USE",
        }
        invalid_values = {
            "missing role": ("LIVE_RECIPIENT", ""),
            "unknown role": ("LIVE_RECIPIENT", "both"),
            "padded role": ("LIVE_RECIPIENT", "self "),
            "swapped slot": ("PUSH_SLOT", "cn"),
            "non-exact slot": ("PUSH_SLOT", "US"),
            "padded slot": ("PUSH_SLOT", " us"),
            "wrong confirmation": ("LIVE_CONFIRMATION", "SEND_CN_ONCE"),
            "padded confirmation": ("LIVE_CONFIRMATION", " SEND_SELF_ONCE"),
            "schedule event": ("GITHUB_EVENT_NAME", "schedule"),
            "non-owner actor": ("GITHUB_ACTOR", "someone-else"),
            "non-owner triggering actor": ("GITHUB_TRIGGERING_ACTOR", "someone-else"),
            "wrong branch": ("GITHUB_REF", "refs/heads/feature"),
            "wrong repository": ("GITHUB_REPOSITORY", "someone/fork"),
            "retry": ("GITHUB_RUN_ATTEMPT", "2"),
            "missing self ID": ("WECHAT_OPENID_SELF", ""),
        }
        for case, (name, bad_value) in invalid_values.items():
            with (
                self.subTest(case=case),
                patch.dict(os.environ, {**valid_env, name: bad_value}, clear=True),
                patch.object(main, "brief_weather") as weather_call,
                patch.object(main, "build_payload_fields") as build,
                patch.object(main, "send_template") as send,
                redirect_stderr(StringIO()),
            ):
                self.assertEqual(main.main(), 2)
                weather_call.assert_not_called()
                build.assert_not_called()
                send.assert_not_called()

    def test_live_cn_requires_config_before_payload_build(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "SEND_MODE": "live",
                    "PUSH_SLOT": "cn",
                    **LIVE_GITHUB_ENV,
                },
                clear=True,
            ),
            patch.object(main, "build_payload_fields") as build,
        ):
            self.assertEqual(main.main(), 2)
            build.assert_not_called()

    def test_live_self_resolves_only_self_openid_with_both_present(self) -> None:
        self_openid = "TEST_SELF_OPENID_DO_NOT_LOG"
        cn_openid = "TEST_CN_OPENID_DO_NOT_USE"
        with patch.dict(
            os.environ,
            {
                "LIVE_RECIPIENT": "self",
                "PUSH_SLOT": "us",
                "WECHAT_OPENID_SELF": self_openid,
                "WECHAT_OPENID_CN": cn_openid,
                "WECHAT_OPENID": "TEST_GENERIC_OPENID_DO_NOT_USE",
            },
            clear=True,
        ):
            self.assertEqual(main.resolve_openid(), self_openid)

    def test_live_cn_resolves_only_cn_openid_with_both_present(self) -> None:
        cn_openid = "TEST_CN_OPENID_DO_NOT_LOG"
        with patch.dict(
            os.environ,
            {
                "LIVE_RECIPIENT": "cn",
                "PUSH_SLOT": "cn",
                "WECHAT_OPENID_SELF": "TEST_SELF_OPENID_DO_NOT_USE",
                "WECHAT_OPENID_CN": cn_openid,
                "WECHAT_OPENID": "TEST_GENERIC_OPENID_DO_NOT_USE",
            },
            clear=True,
        ):
            self.assertEqual(main.resolve_openid(), cn_openid)

    def test_resolve_openid_rejects_non_exact_slot(self) -> None:
        for role, slot in (("self", "US"), ("cn", "CN")):
            with (
                self.subTest(role=role),
                patch.dict(
                    os.environ,
                    {
                        "LIVE_RECIPIENT": role,
                        "PUSH_SLOT": slot,
                        "WECHAT_OPENID_SELF": "TEST_SELF_OPENID",
                        "WECHAT_OPENID_CN": "TEST_CN_OPENID",
                    },
                    clear=True,
                ),
            ):
                with self.assertRaises(main.ConfigError):
                    main.resolve_openid()

    def test_resolve_openid_rejects_padded_role_or_slot(self) -> None:
        base_env = {
            "LIVE_RECIPIENT": "self",
            "PUSH_SLOT": "us",
            "WECHAT_OPENID_SELF": "TEST_SELF_OPENID",
            "WECHAT_OPENID_CN": "TEST_CN_OPENID",
        }
        for name, padded_value in (
            ("LIVE_RECIPIENT", "self "),
            ("PUSH_SLOT", " us"),
        ):
            with (
                self.subTest(name=name),
                patch.dict(
                    os.environ,
                    {**base_env, name: padded_value},
                    clear=True,
                ),
            ):
                with self.assertRaises(main.ConfigError):
                    main.resolve_openid()

    def test_live_self_main_sends_only_to_self_id(self) -> None:
        stdout = StringIO()
        self_openid = "TEST_SELF_OPENID_DO_NOT_LOG"
        cn_openid = "TEST_CN_OPENID_DO_NOT_USE"
        with (
            patch.dict(
                os.environ,
                {
                    "SEND_MODE": "live",
                    "PUSH_SLOT": "us",
                    **LIVE_GITHUB_ENV,
                    "LIVE_RECIPIENT": "self",
                    "LIVE_CONFIRMATION": "SEND_SELF_ONCE",
                    "WECHAT_APP_ID": "TEST_APP_ID",
                    "WECHAT_APP_SECRET": "TEST_SECRET_DO_NOT_LOG",
                    "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE_DO_NOT_LOG",
                    "WECHAT_OPENID_SELF": self_openid,
                    "WECHAT_OPENID_CN": cn_openid,
                },
                clear=True,
            ),
            patch.object(main, "build_payload_fields", return_value=TEST_FIELDS),
            patch.object(
                main, "send_template", return_value={"errcode": 0, "msgid": "123"}
            ) as send,
            redirect_stdout(stdout),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 0)
            self.assertEqual(send.call_args.kwargs["openid"], self_openid)
            for sentinel in (self_openid, cn_openid, "TEST_SECRET_DO_NOT_LOG"):
                self.assertNotIn(sentinel, stdout.getvalue())

    def test_live_cn_uses_only_dedicated_cn_openid(self) -> None:
        stdout = StringIO()
        cn_openid = "TEST_CN_OPENID_DO_NOT_LOG"
        generic_openid = "TEST_GENERIC_OPENID_DO_NOT_USE"
        with (
            patch.dict(
                os.environ,
                {
                    "SEND_MODE": "live",
                    "PUSH_SLOT": "cn",
                    **LIVE_GITHUB_ENV,
                    "WECHAT_APP_ID": "TEST_APP_ID",
                    "WECHAT_APP_SECRET": "TEST_SECRET_DO_NOT_LOG",
                    "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE_DO_NOT_LOG",
                    "WECHAT_OPENID_CN": cn_openid,
                    "WECHAT_OPENID_SELF": "TEST_SELF_OPENID_DO_NOT_USE",
                    "WECHAT_OPENID": generic_openid,
                },
                clear=True,
            ),
            patch.object(main, "build_payload_fields", return_value=TEST_FIELDS),
            patch.object(
                main, "send_template", return_value={"errcode": 0, "msgid": "123"}
            ) as send,
            redirect_stdout(stdout),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 0)
            self.assertEqual(send.call_args.kwargs["openid"], cn_openid)
            self.assertNotEqual(send.call_args.kwargs["openid"], generic_openid)
            for sentinel in (
                cn_openid,
                generic_openid,
                "TEST_SELF_OPENID_DO_NOT_USE",
                "TEST_SECRET_DO_NOT_LOG",
                "TEST_TEMPLATE_DO_NOT_LOG",
            ):
                self.assertNotIn(sentinel, stdout.getvalue())


class DateTests(unittest.TestCase):
    def assert_english_payload(self, values: dict[str, str]) -> None:
        for key, value in values.items():
            with self.subTest(field=key):
                if key in {"weather_a", "weather_b"}:
                    self.assertTrue(value.replace("°", "").isascii())
                elif key == "love_line":
                    generated_line, separator, known_line = value.partition("\n")
                    self.assertTrue(generated_line.isascii())
                    self.assertRegex(known_line, r"\AKnown: ≈[0-9]+ days\Z")
                    self.assertEqual(separator, "\n")
                else:
                    self.assertTrue(value.isascii())

    def test_known_days_and_love_line_survive_template_rendering(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "PUSH_SLOT": "cn",
                    "KNOWN_START_DATE": "2019-09-02",
                    "LOVE_START_DATE": "2026-07-08",
                    "NEXT_MEET_DATE": "2026-12-20",
                },
                clear=True,
            ),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Thinking of you"),
        ):
            fields = main.build_payload_fields()
            self.assertEqual(fields["love_days"], "71 days")
            self.assertEqual(fields["meet_days"], "in 95 days | Thinking of you")
            self.assertEqual(fields["love_line"], "Thinking of you\nKnown: ≈2572 days")
            self.assertEqual(
                wechat.build_template_data(fields)["love_line"]["value"],
                "Thinking of you\nKnown: ≈2572 days",
            )
            self.assert_english_payload(fields)

    def test_missing_known_start_date_uses_approximate_anchor(self) -> None:
        with (
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
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Thinking of you"),
        ):
            fields = main.build_payload_fields()
            self.assertEqual(fields["love_line"], "Thinking of you\nKnown: ≈2572 days")
            self.assertEqual(fields["love_days"], "71 days")
            self.assertEqual(fields["meet_days"], "in 95 days | Thinking of you")

    def test_invalid_known_start_date_fails_before_weather(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "PUSH_SLOT": "cn",
                    "KNOWN_START_DATE": "not-a-date",
                    "LOVE_START_DATE": "2026-07-08",
                    "NEXT_MEET_DATE": "2026-12-20",
                },
                clear=True,
            ),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "brief_weather") as weather_call,
            patch.object(main, "generate_love_line", return_value="Thinking of you"),
        ):
            with self.assertRaises(ValueError):
                main.build_payload_fields()
            weather_call.assert_not_called()

    def test_generated_line_cannot_add_non_english_characters(self) -> None:
        for generated in ("Thinking ≈ of you", "Thinking ° of you", "早安"):
            with (
                self.subTest(generated=generated),
                patch.dict(
                    os.environ,
                    {
                        "PUSH_SLOT": "cn",
                        "LOVE_START_DATE": "2026-07-08",
                        "NEXT_MEET_DATE": "2026-12-20",
                    },
                    clear=True,
                ),
                patch.object(main, "local_today", return_value=date(2026, 9, 16)),
                patch.object(main, "local_now_str", return_value="08:00"),
                patch.object(main, "brief_weather", return_value="Clear 20°C"),
                patch.object(main, "generate_love_line", return_value=generated),
            ):
                with self.assertRaises(main.ConfigError):
                    main.build_payload_fields()

    def test_weather_cannot_add_approximation_sign(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "PUSH_SLOT": "cn",
                    "LOVE_START_DATE": "2026-07-08",
                    "NEXT_MEET_DATE": "2026-12-20",
                },
                clear=True,
            ),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear ≈20°C"),
            patch.object(main, "generate_love_line", return_value="Thinking of you"),
        ):
            with self.assertRaises(main.ConfigError):
                main.build_payload_fields()

    def test_slots_use_their_own_local_calendar_date(self) -> None:
        base_env = {
            "LOVE_START_DATE": "2026-09-14",
            "NEXT_MEET_DATE": "2026-09-20",
            "CITY_A_TZ": "America/Detroit",
            "CITY_B_TZ": "Asia/Shanghai",
        }
        cases = (
            ("cn", "Asia/Shanghai", date(2026, 9, 15), "2 days", "in 5 days"),
            ("us", "America/Detroit", date(2026, 9, 14), "1 day", "in 6 days"),
        )
        for slot, expected_tz, local_date, love_text, meet_text in cases:
            with (
                self.subTest(slot=slot),
                patch.dict(os.environ, {**base_env, "PUSH_SLOT": slot}, clear=True),
                patch.object(main, "local_today", return_value=local_date) as local_today,
                patch.object(main, "local_now_str", return_value="08:00"),
                patch.object(main, "brief_weather", return_value="Unavailable"),
                patch.object(main, "generate_love_line", return_value="Thinking of you"),
            ):
                fields = main.build_payload_fields()
                local_today.assert_called_once_with(expected_tz)
                self.assertEqual(fields["greeting"], "Good morning, love!")
                self.assertEqual(fields["love_days"], love_text)
                self.assertEqual(fields["meet_days"], f"{meet_text} | Thinking of you")
                self.assert_english_payload(fields)

    def test_meeting_has_three_states(self) -> None:
        today = date(2026, 9, 15)
        self.assertEqual(dates.meet_status("2026-09-16", today), "in 1 day")
        self.assertEqual(dates.meet_status("2026-09-15", today), "today")
        self.assertEqual(dates.meet_status("2026-09-14", today), "date passed")

    def test_non_english_city_cannot_reach_recipient(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "CITY_A": "安娜堡",
                    "PUSH_SLOT": "cn",
                    "LOVE_START_DATE": "2026-09-14",
                    "NEXT_MEET_DATE": "2026-09-20",
                },
                clear=True,
            ),
            patch.object(main, "brief_weather") as weather_call,
        ):
            with self.assertRaises(main.ConfigError):
                main.build_payload_fields()
            weather_call.assert_not_called()

    def test_final_preview_values_remain_english_after_truncation(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "CITY_A": "San Francisco",
                    "PUSH_SLOT": "cn",
                    "LOVE_START_DATE": "2026-09-14",
                    "NEXT_MEET_DATE": "2026-09-20",
                },
                clear=True,
            ),
            patch.object(main, "brief_weather", return_value="Unavailable"),
            patch.object(main, "generate_love_line", return_value="Thinking of you"),
        ):
            data = wechat.build_template_data(main.build_payload_fields())
            self.assert_english_payload(
                {key: value["value"] for key, value in data.items()}
            )

    def test_keyless_weather_source_is_attributed(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "PUSH_SLOT": "cn",
                    "LOVE_START_DATE": "2026-07-08",
                    "NEXT_MEET_DATE": "2026-12-20",
                },
                clear=True,
            ),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Thinking of you"),
        ):
            fields = main.build_payload_fields()
            expected = (
                "Open-Meteo https://open-meteo.com | GeoNames | "
                "CC BY 4.0 https://creativecommons.org/licenses/by/4.0/ | adapted"
            )
            self.assertEqual(fields["weather_source"], expected)
            self.assertEqual(
                wechat.build_template_data(fields)["weather_source"]["value"], expected
            )


class WeChatSafetyTests(unittest.TestCase):
    @staticmethod
    def response(data: object) -> Mock:
        response = Mock()
        response.status_code = 200
        response.json.return_value = data
        response.raise_for_status.return_value = None
        return response

    def test_token_redirect_is_rejected_without_forwarding_secret(self) -> None:
        response = self.response({"access_token": "fake"})
        response.status_code = 302
        with patch.object(wechat.requests, "get", return_value=response) as request:
            with self.assertRaises(wechat.WeChatAPIError):
                wechat.get_access_token("app", "secret")
            self.assertIs(request.call_args.kwargs["allow_redirects"], False)

    def test_template_redirect_is_rejected_without_forwarding_payload(self) -> None:
        response = self.response({"errcode": 0, "errmsg": "ok", "msgid": 123})
        response.status_code = 307
        with patch.object(wechat.requests, "post", return_value=response) as request:
            with self.assertRaises(wechat.WeChatAPIError):
                wechat.send_template("openid", "template", {"greeting": "hi"}, "token")
            self.assertIs(request.call_args.kwargs["allow_redirects"], False)

    def test_empty_json_token_response_fails(self) -> None:
        with patch.object(wechat.requests, "get", return_value=self.response({})):
            with self.assertRaises(wechat.WeChatAPIError):
                wechat.get_access_token("app", "secret")

    def test_non_string_token_response_fails(self) -> None:
        with patch.object(
            wechat.requests,
            "get",
            return_value=self.response({"access_token": 123}),
        ):
            with self.assertRaises(wechat.WeChatAPIError):
                wechat.get_access_token("app", "secret")

    def test_nonzero_errcode_fails(self) -> None:
        response = self.response({"errcode": 40001, "msgid": "123"})
        with patch.object(wechat.requests, "post", return_value=response):
            with self.assertRaises(wechat.WeChatAPIError):
                wechat.send_template(
                    "openid", "template", {"greeting": "hi"}, "token"
                )

    def test_empty_json_send_response_fails(self) -> None:
        with patch.object(
            wechat.requests, "post", return_value=self.response({})
        ):
            with self.assertRaises(wechat.WeChatAPIError):
                wechat.send_template(
                    "openid", "template", {"greeting": "hi"}, "token"
                )

    def test_missing_errcode_fails_even_with_msgid(self) -> None:
        response = self.response({"msgid": "123"})
        with patch.object(wechat.requests, "post", return_value=response):
            with self.assertRaises(wechat.WeChatAPIError):
                wechat.send_template(
                    "openid", "template", {"greeting": "hi"}, "token"
                )

    def test_missing_msgid_fails(self) -> None:
        response = self.response({"errcode": 0})
        with patch.object(wechat.requests, "post", return_value=response):
            with self.assertRaises(wechat.WeChatAPIError):
                wechat.send_template(
                    "openid", "template", {"greeting": "hi"}, "token"
                )

    def test_response_types_are_strict(self) -> None:
        invalid_responses = (
            {"errcode": False, "errmsg": "ok", "msgid": "123"},
            {"errcode": "0", "errmsg": "ok", "msgid": "123"},
            {"errcode": 0, "errmsg": "ok", "msgid": False},
            {"errcode": 0, "errmsg": "ok", "msgid": 0},
            {"errcode": 0, "errmsg": "ok", "msgid": -1},
            {"errcode": 0, "errmsg": "ok", "msgid": "0"},
            {"errcode": 0, "errmsg": "ok", "msgid": "abc"},
            {"errcode": 0, "errmsg": "not ok", "msgid": "123"},
        )
        for result in invalid_responses:
            with self.subTest(result=result), patch.object(
                wechat.requests, "post", return_value=self.response(result)
            ):
                with self.assertRaises(wechat.WeChatAPIError):
                    wechat.send_template(
                        "openid", "template", {"greeting": "hi"}, "token"
                    )

    def test_success_returns_only_safe_fields(self) -> None:
        response = self.response(
            {"errcode": 0, "errmsg": "ok", "msgid": 123, "extra": "ignored"}
        )
        with patch.object(wechat.requests, "post", return_value=response):
            self.assertEqual(
                wechat.send_template(
                    "openid", "template", {"greeting": "hi"}, "token"
                ),
                {"errcode": 0, "msgid": "123"},
            )

    def test_network_error_does_not_leak_secret_or_token(self) -> None:
        secret = "TEST_WECHAT_SECRET_DO_NOT_LOG"
        token = "TEST_ACCESS_TOKEN_DO_NOT_LOG"
        with patch.object(
            wechat.requests,
            "get",
            side_effect=requests.RequestException(f"url?secret={secret}"),
        ):
            with self.assertRaises(wechat.WeChatAPIError) as caught:
                wechat.get_access_token("app", secret)
            self.assertNotIn(secret, str(caught.exception))

        with patch.object(
            wechat.requests,
            "post",
            side_effect=requests.RequestException(f"url?access_token={token}"),
        ):
            with self.assertRaises(wechat.WeChatAPIError) as caught:
                wechat.send_template(
                    "openid", "template", {"greeting": "hi"}, token
                )
            self.assertNotIn(token, str(caught.exception))

    def test_main_unknown_send_error_is_redacted(self) -> None:
        sentinel = "TEST_UNEXPECTED_SECRET_DO_NOT_LOG"
        stdout = StringIO()
        stderr = StringIO()
        with (
            patch.dict(
                os.environ,
                {
                    "SEND_MODE": "live",
                    "PUSH_SLOT": "cn",
                    **LIVE_GITHUB_ENV,
                    "WECHAT_APP_ID": "TEST_APP_ID",
                    "WECHAT_APP_SECRET": "TEST_APP_SECRET",
                    "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE_ID",
                    "WECHAT_OPENID_CN": "TEST_CN_OPENID",
                },
                clear=True,
            ),
            patch.object(main, "build_payload_fields", return_value=TEST_FIELDS),
            patch.object(main, "send_template", side_effect=RuntimeError(sentinel)),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(main.main(), 1)
            self.assertNotIn(sentinel, stdout.getvalue())
            self.assertNotIn(sentinel, stderr.getvalue())
            self.assertIn("详情已脱敏", stderr.getvalue())

    def test_main_success_log_whitelists_fields(self) -> None:
        sentinel = "TEST_EXTRA_SECRET_DO_NOT_LOG"
        stdout = StringIO()
        with (
            patch.dict(
                os.environ,
                {
                    "SEND_MODE": "live",
                    "PUSH_SLOT": "cn",
                    **LIVE_GITHUB_ENV,
                    "WECHAT_APP_ID": "TEST_APP_ID",
                    "WECHAT_APP_SECRET": "TEST_APP_SECRET",
                    "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE_ID",
                    "WECHAT_OPENID_CN": "TEST_CN_OPENID",
                },
                clear=True,
            ),
            patch.object(main, "build_payload_fields", return_value=TEST_FIELDS),
            patch.object(
                main,
                "send_template",
                return_value={
                    "errcode": 0,
                    "msgid": "123",
                    "extra": sentinel,
                    "ok": False,
                },
            ),
            redirect_stdout(stdout),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 0)
            self.assertEqual(
                stdout.getvalue().strip(),
                '{"ok": true, "errcode": 0, "msgid": "123"}',
            )
            self.assertNotIn(sentinel, stdout.getvalue())


class QWeatherTests(unittest.TestCase):
    def test_key_uses_header_not_query(self) -> None:
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": "200", "location": [{"id": "1"}]}
        with patch.dict(
            os.environ,
                {
                    "QWEATHER_KEY": "TEST_QWEATHER_KEY",
                    "QWEATHER_API_HOST": "abc123.qweatherapi.com",
            },
            clear=True,
        ), patch.object(weather.requests, "get", return_value=response) as request:
            self.assertEqual(weather.lookup_city("Shanghai"), {"id": "1"})
            kwargs = request.call_args.kwargs
            self.assertEqual(kwargs["headers"], {"X-QW-Api-Key": "TEST_QWEATHER_KEY"})
            self.assertEqual(kwargs["params"], {"location": "Shanghai"})
            self.assertNotIn("key", kwargs["params"])
            self.assertIs(kwargs["allow_redirects"], False)

    def test_weather_now_key_uses_header_not_query(self) -> None:
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": "200", "now": {"text": "Sunny"}}
        with patch.dict(
            os.environ,
            {
                "QWEATHER_KEY": "TEST_QWEATHER_KEY",
                "QWEATHER_API_HOST": "https://abc123.qweatherapi.com",
            },
            clear=True,
        ), patch.object(weather.requests, "get", return_value=response) as request:
            self.assertEqual(weather.weather_now("1"), {"text": "Sunny"})
            kwargs = request.call_args.kwargs
            self.assertEqual(kwargs["headers"], {"X-QW-Api-Key": "TEST_QWEATHER_KEY"})
            self.assertEqual(kwargs["params"], {"location": "1", "lang": "en"})
            self.assertIs(kwargs["allow_redirects"], False)

    def test_weather_redirect_response_is_rejected(self) -> None:
        response = Mock()
        response.status_code = 302
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": "200", "location": [{"id": "1"}]}
        with patch.dict(
            os.environ,
            {"QWEATHER_KEY": "TEST_KEY", "QWEATHER_API_HOST": "abc123.qweatherapi.com"},
            clear=True,
        ), patch.object(weather.requests, "get", return_value=response):
            self.assertIsNone(weather.lookup_city("Shanghai"))

    def test_non_ascii_temperature_degrades_to_english(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"QWEATHER_KEY": "TEST_KEY", "QWEATHER_API_HOST": "abc123.qweatherapi.com"},
                clear=True,
            ),
            patch.object(weather, "lookup_city", return_value={"id": "1"}),
            patch.object(weather, "weather_now", return_value={"text": "Sunny", "temp": "１２"}),
        ):
            self.assertEqual(weather.brief_weather("Shanghai"), weather.UNAVAILABLE_REQUEST)

    def test_non_english_weather_response_degrades_to_english(self) -> None:
        env = {
            "QWEATHER_KEY": "TEST_QWEATHER_KEY",
            "QWEATHER_API_HOST": "https://abc123.qweatherapi.com",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(weather, "lookup_city", return_value={"id": "1"}),
            patch.object(
                weather, "weather_now", return_value={"text": "晴", "temp": "12"}
            ),
        ):
            self.assertEqual(weather.brief_weather("Shanghai"), weather.UNAVAILABLE_REQUEST)
            self.assertTrue(weather.UNAVAILABLE_REQUEST.isascii())
            self.assertLessEqual(len(weather.UNAVAILABLE_REQUEST), 16)
            self.assertTrue(weather.UNAVAILABLE_CONFIG.isascii())
            self.assertLessEqual(len(weather.UNAVAILABLE_CONFIG), 16)

    def test_long_english_weather_keeps_readable_description(self) -> None:
        env = {
            "QWEATHER_KEY": "TEST_QWEATHER_KEY",
            "QWEATHER_API_HOST": "https://abc123.qweatherapi.com",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(weather, "lookup_city", return_value={"id": "1"}),
            patch.object(
                weather,
                "weather_now",
                return_value={"text": "Mostly cloudy", "temp": "12"},
            ),
        ):
            self.assertEqual(weather.brief_weather("Shanghai"), "Mostly cloudy")


    def test_missing_host_uses_keyless_fallback_without_leaking_key(self) -> None:
        with patch.dict(
            os.environ, {"QWEATHER_KEY": "TEST_QWEATHER_KEY"}, clear=True
        ), patch.object(weather.requests, "get", side_effect=requests.Timeout) as request:
            self.assertEqual(weather.brief_weather("Shanghai"), weather.UNAVAILABLE_CONFIG)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[0], "https://geocoding-api.open-meteo.com/v1/search")
            self.assertNotIn("headers", request.call_args.kwargs)

    def test_missing_key_uses_keyless_fallback(self) -> None:
        with patch.dict(
            os.environ,
            {"QWEATHER_API_HOST": "https://abc123.qweatherapi.com"},
            clear=True,
        ), patch.object(weather.requests, "get", side_effect=requests.Timeout) as request:
            self.assertEqual(weather.brief_weather("Shanghai"), weather.UNAVAILABLE_CONFIG)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[0], "https://geocoding-api.open-meteo.com/v1/search")

    def test_malformed_json_shapes_degrade(self) -> None:
        env = {
            "QWEATHER_KEY": "TEST_QWEATHER_KEY",
            "QWEATHER_API_HOST": "https://abc123.qweatherapi.com",
        }
        malformed_lookup = (
            [],
            "not-an-object",
            {"code": "200", "location": "not-a-list"},
            {"code": "200", "location": [123]},
        )
        for body in malformed_lookup:
            response = Mock()
            response.status_code = 200
            response.raise_for_status.return_value = None
            response.json.return_value = body
            with self.subTest(endpoint="lookup", body=body), patch.dict(
                os.environ, env, clear=True
            ), patch.object(weather.requests, "get", return_value=response):
                self.assertIsNone(weather.lookup_city("Shanghai"))

        malformed_weather = (
            [],
            "not-an-object",
            {"code": "200", "now": "not-an-object"},
        )
        for body in malformed_weather:
            response = Mock()
            response.status_code = 200
            response.raise_for_status.return_value = None
            response.json.return_value = body
            with self.subTest(endpoint="weather", body=body), patch.dict(
                os.environ, env, clear=True
            ), patch.object(weather.requests, "get", return_value=response):
                self.assertIsNone(weather.weather_now("1"))

    def test_untrusted_host_never_receives_key(self) -> None:
        unsafe_hosts = (
            "https://attacker.example",
            "http://abc123.qweatherapi.com",
            "https://abc123.qweatherapi.com/path",
            "https://user@abc123.qweatherapi.com",
        )
        for host in unsafe_hosts:
            with self.subTest(host=host), patch.dict(
                os.environ,
                {
                    "QWEATHER_KEY": "TEST_QWEATHER_KEY_DO_NOT_SEND",
                    "QWEATHER_API_HOST": host,
                },
                clear=True,
            ), patch.object(weather.requests, "get", side_effect=requests.Timeout) as request:
                self.assertEqual(
                    weather.brief_weather("Shanghai"), weather.UNAVAILABLE_CONFIG
                )
                self.assertEqual(request.call_count, 1)
                self.assertEqual(request.call_args.args[0], "https://geocoding-api.open-meteo.com/v1/search")
                self.assertNotIn("headers", request.call_args.kwargs)

    def test_template_contains_qweather_attribution(self) -> None:
        data = wechat.build_template_data(
            {"weather_source": "QWeather https://www.qweather.com"}
        )
        self.assertEqual(
            data["weather_source"]["value"],
            "QWeather https://www.qweather.com",
        )


class OpenMeteoTests(unittest.TestCase):
    def test_keyless_forecast_for_shanghai_is_short_english_weather(self) -> None:
        geo = Mock(status_code=200)
        geo.json.return_value = {
            "results": [{"country_code": "CN", "latitude": 31.22222, "longitude": 121.45806}]
        }
        forecast = Mock(status_code=200)
        forecast.json.return_value = {
            "current": {"temperature_2m": 23.3, "weather_code": 2}
        }
        with patch.dict(os.environ, {}, clear=True), patch.object(
            weather.requests, "get", side_effect=[geo, forecast]
        ) as request:
            report = weather.brief_weather("Shanghai")
            self.assertEqual(report, "Ptly cloudy 23°C")
            self.assertLessEqual(len(report), 16)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(
                request.call_args_list[0].args[0],
                "https://geocoding-api.open-meteo.com/v1/search",
            )
            self.assertEqual(request.call_args_list[0].kwargs["params"]["countryCode"], "CN")
            self.assertEqual(
                request.call_args_list[1].args[0], "https://api.open-meteo.com/v1/forecast"
            )
            self.assertTrue(all(call.kwargs["allow_redirects"] is False for call in request.call_args_list))
            self.assertTrue(all("headers" not in call.kwargs for call in request.call_args_list))

    def test_keyless_redirect_is_rejected(self) -> None:
        geo = Mock(status_code=302)
        geo.json.return_value = {
            "results": [{"country_code": "CN", "latitude": 31.22222, "longitude": 121.45806}]
        }
        with patch.dict(os.environ, {}, clear=True), patch.object(
            weather.requests, "get", return_value=geo
        ) as request:
            self.assertEqual(weather.brief_weather("Shanghai"), weather.UNAVAILABLE_CONFIG)
            self.assertEqual(request.call_count, 1)
            self.assertIs(request.call_args.kwargs["allow_redirects"], False)

    def test_extreme_coordinates_degrade_without_crashing(self) -> None:
        geo = Mock(status_code=200)
        geo.json.return_value = {
            "results": [{"country_code": "CN", "latitude": 10**1000, "longitude": 121.4}]
        }
        with patch.dict(os.environ, {}, clear=True), patch.object(
            weather.requests, "get", return_value=geo
        ) as request:
            self.assertEqual(weather.brief_weather("Shanghai"), weather.UNAVAILABLE_CONFIG)
            self.assertEqual(request.call_count, 1)

    def test_extreme_temperature_degrades_without_crashing(self) -> None:
        geo = Mock(status_code=200)
        geo.json.return_value = {
            "results": [{"country_code": "CN", "latitude": 31.2, "longitude": 121.4}]
        }
        forecast = Mock(status_code=200)
        forecast.json.return_value = {
            "current": {"temperature_2m": 10**1000, "weather_code": 0}
        }
        with patch.dict(os.environ, {}, clear=True), patch.object(
            weather.requests, "get", side_effect=[geo, forecast]
        ):
            self.assertEqual(weather.brief_weather("Shanghai"), weather.UNAVAILABLE_CONFIG)

    def test_freezing_and_hail_codes_keep_important_weather_meaning(self) -> None:
        cases = ((56, "Icy driz 23°C"), (66, "Icy rain 23°C"), (96, "Hail storm 23°C"))
        for code, expected in cases:
            geo = Mock(status_code=200)
            geo.json.return_value = {
                "results": [{"country_code": "CN", "latitude": 31.2, "longitude": 121.4}]
            }
            forecast = Mock(status_code=200)
            forecast.json.return_value = {
                "current": {"temperature_2m": 23, "weather_code": code}
            }
            with self.subTest(code=code), patch.dict(os.environ, {}, clear=True), patch.object(
                weather.requests, "get", side_effect=[geo, forecast]
            ):
                self.assertEqual(weather.brief_weather("Shanghai"), expected)


class DocumentationTests(unittest.TestCase):
    def test_wechat_template_is_english_and_keeps_existing_variables(self) -> None:
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        section = readme.split("## 微信模板", 1)[1]
        template = section.split("```text\n", 1)[1].split("\n```", 1)[0]
        self.assertEqual(
            template,
            (
                "{{greeting.DATA}}\n"
                "A: {{city_a.DATA}} {{time_a.DATA}} {{weather_a.DATA}}\n"
                "B: {{city_b.DATA}} {{time_b.DATA}} {{weather_b.DATA}}\n"
                "Together: {{love_days.DATA}}\n"
                "Next meeting: {{meet_days.DATA}}\n"
                "{{love_line.DATA}}\n"
                "Weather: {{weather_source.DATA}}"
            ),
        )

    def test_daily_documentation_separates_recipient_gates(self) -> None:
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("`ENABLE_CN_DAILY`", readme)
        self.assertIn("`ENABLE_SELF_DAILY`", readme)
        self.assertIn("`1`", readme)
        self.assertIn("本人手机已确认修复后的英文情话显示", readme)
        self.assertIn("女友手机尚未确认", readme)
        self.assertIn("上海 09:00", readme)
        self.assertIn("`daily-both`", readme)
        self.assertIn("关闭", readme)


class WorkflowPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "daily-push.yml"
        ).read_text(encoding="utf-8")

    def test_timezone_schedules_and_matching_conditions(self) -> None:
        self.assertIn('cron: "0 9 * * *"', self.workflow)
        self.assertIn('timezone: "Asia/Shanghai"', self.workflow)
        self.assertEqual(self.workflow.count('    - cron: "0 9 * * *"'), 1)
        self.assertNotIn('timezone: "America/Detroit"', self.workflow)
        self.assertEqual(self.workflow.count("github.event.schedule == '0 9 * * *'"), 6)

    def test_stage_c_manual_gate_is_exact(self) -> None:
        self.assertIn('[ "$REQUEST_SLOT" != "cn" ]', self.workflow)
        self.assertIn(
            '[ "$REQUEST_CONFIRMATION" != "SEND_CN_ONCE" ]', self.workflow
        )
        self.assertIn("          - live-self", self.workflow)
        self.assertIn("            live-self)", self.workflow)
        self.assertIn('[ "$REQUEST_SLOT" != "us" ]', self.workflow)
        self.assertIn(
            '[ "$REQUEST_CONFIRMATION" != "SEND_SELF_ONCE" ]', self.workflow
        )
        self.assertIn('REQUEST_REF: ${{ github.ref }}', self.workflow)
        self.assertIn('REQUEST_ATTEMPT: ${{ github.run_attempt }}', self.workflow)
        self.assertIn("          - daily-both", self.workflow)
        self.assertIn('REQUEST_DELIVERY_DATE: ${{ inputs.delivery_date }}', self.workflow)
        self.assertIn('daily-both requires slot=both, blank confirmation, and today in Shanghai.', self.workflow)
        self.assertEqual(self.workflow.count("github.ref == 'refs/heads/main'"), 6)
        self.assertEqual(self.workflow.count("github.run_attempt == '1'"), 6)

    def test_preview_jobs_have_no_wechat_credentials(self) -> None:
        self.assertIn("  live-self:", self.workflow)
        cn_job = self.workflow.split("  preview-cn:", 1)[1].split(
            "  preview-us:", 1
        )[0]
        us_job = self.workflow.split("  preview-us:", 1)[1].split(
            "  preview-both:", 1
        )[0]
        both_job = self.workflow.split("  preview-both:", 1)[1].split(
            "  live-self:", 1
        )[0]
        for job in (cn_job, us_job, both_job):
            self.assertIn("SEND_MODE: dry-run", job)
            self.assertNotIn("WECHAT_APP_ID:", job)
            self.assertNotIn("WECHAT_APP_SECRET:", job)
            self.assertNotIn("WECHAT_TEMPLATE_ID:", job)
            self.assertNotIn("WECHAT_OPENID_CN:", job)
            self.assertNotIn("WECHAT_OPENID_SELF:", job)
            self.assertNotIn("SEND_MODE: ${{", job)

    def test_deepseek_is_available_in_each_message_job(self) -> None:
        self.assertEqual(self.workflow.count("DEEPSEEK_API_KEY:"), 8)
        self.assertNotIn("GEMINI_API_KEY:", self.workflow)

    def test_manual_live_jobs_are_isolated_by_recipient_and_event(self) -> None:
        self.assertIn("  live-self:", self.workflow)
        self_job = self.workflow.split("  live-self:", 1)[1].split(
            "  live-cn:", 1
        )[0]
        cn_job = self.workflow.split("  live-cn:", 1)[1].split(
            "  scheduled-cn:", 1
        )[0]
        for mode, slot, confirmation, recipient, job in (
            ("live-self", "us", "SEND_SELF_ONCE", "self", self_job),
            ("live-cn", "cn", "SEND_CN_ONCE", "cn", cn_job),
        ):
            with self.subTest(mode=mode):
                self.assertIn("needs: validate-dispatch", job)
                self.assertIn("needs.validate-dispatch.result == 'success'", job)
                self.assertIn("github.event_name == 'workflow_dispatch'", job)
                self.assertIn(f"inputs.mode == '{mode}'", job)
                self.assertIn(f"inputs.slot == '{slot}'", job)
                self.assertIn(f"inputs.confirmation == '{confirmation}'", job)
                self.assertIn("github.repository == 'carloshuangspec/wechat-ldr-daily-push'", job)
                self.assertIn("github.ref == 'refs/heads/main'", job)
                self.assertIn("github.actor == 'carloshuangspec'", job)
                self.assertIn("github.triggering_actor == 'carloshuangspec'", job)
                self.assertIn("github.run_attempt == '1'", job)
                self.assertIn(f"PUSH_SLOT: {slot}", job)
                self.assertIn("SEND_MODE: live", job)
                self.assertIn(f"LIVE_RECIPIENT: {recipient}", job)
                self.assertIn("LIVE_CONFIRMATION: ${{ inputs.confirmation }}", job)
                self.assertIn("WECHAT_APP_ID: ${{ secrets.WECHAT_APP_ID }}", job)
                self.assertIn("WECHAT_APP_SECRET: ${{ secrets.WECHAT_APP_SECRET }}", job)
                self.assertIn("WECHAT_TEMPLATE_ID: ${{ secrets.WECHAT_TEMPLATE_ID }}", job)
                self.assertNotIn("github.event_name == 'schedule'", job)
                self.assertIn("actions/checkout@v7", job)
                self.assertIn("actions/setup-python@v7", job)
                self.assertIn("python -m unittest discover -s tests -v", job)

        self.assertIn("WECHAT_OPENID_SELF: ${{ secrets.WECHAT_OPENID_SELF }}", self_job)
        self.assertNotIn("WECHAT_OPENID_CN:", self_job)
        self.assertIn("WECHAT_OPENID_CN: ${{ secrets.WECHAT_OPENID_CN }}", cn_job)
        self.assertNotIn("WECHAT_OPENID_SELF:", cn_job)
        self.assertEqual(self.workflow.count("WECHAT_APP_SECRET:"), 5)
        self.assertEqual(self.workflow.count("WECHAT_OPENID_SELF:"), 3)
        self.assertEqual(self.workflow.count("WECHAT_OPENID_CN:"), 3)
        self.assertNotIn("WECHAT_OPENID_US:", self.workflow)
        self.assertEqual(self.workflow.count("SEND_MODE: live"), 5)
        self.assertNotIn("DRY_RUN:", self.workflow)
        self.assertNotIn("vars.DRY_RUN", self.workflow)

    def test_scheduled_cn_job_is_exact_and_uses_only_cn_credentials(self) -> None:
        self.assertIn("  scheduled-cn:", self.workflow)
        job = self.workflow.split("  scheduled-cn:", 1)[1].split("  scheduled-self:", 1)[0]
        for fragment in (
            "needs: validate-dispatch",
            "needs.validate-dispatch.result == 'success'",
            "github.event_name == 'schedule'",
            "github.event.schedule == '0 9 * * *'",
            "vars.ENABLE_CN_DAILY == '1'",
            "github.repository == 'carloshuangspec/wechat-ldr-daily-push'",
            "github.ref == 'refs/heads/main'",
            "github.run_attempt == '1'",
            "PUSH_SLOT: cn",
            "SEND_MODE: live",
            "LIVE_RECIPIENT: cn",
            "GITHUB_EVENT_SCHEDULE: ${{ github.event.schedule }}",
            "ENABLE_CN_DAILY: ${{ vars.ENABLE_CN_DAILY }}",
            "WECHAT_APP_ID: ${{ secrets.WECHAT_APP_ID }}",
            "WECHAT_APP_SECRET: ${{ secrets.WECHAT_APP_SECRET }}",
            "WECHAT_TEMPLATE_ID: ${{ secrets.WECHAT_TEMPLATE_ID }}",
            "WECHAT_OPENID_CN: ${{ secrets.WECHAT_OPENID_CN }}",
            "actions/checkout@v7",
            "actions/setup-python@v7",
            "python -m unittest discover -s tests -v",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, job)
        self.assertNotIn("WECHAT_OPENID_SELF:", job)
        self.assertNotIn("LIVE_CONFIRMATION:", job)
        self.assertNotIn("SEND_CN_ONCE", job)
        self.assertNotIn("inputs.mode", job)

    def test_known_start_date_reaches_every_message_job(self) -> None:
        self.assertEqual(
            self.workflow.count("KNOWN_START_DATE: ${{ vars.KNOWN_START_DATE }}"), 8
        )

    def test_workflow_uses_current_node24_actions_and_fixed_concurrency(self) -> None:
        self.assertEqual(self.workflow.count("actions/checkout@v7"), 9)
        self.assertEqual(self.workflow.count("actions/setup-python@v7"), 9)
        self.assertIn("group: wechat-ldr-daily-push-stage-c", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)


if __name__ == "__main__":
    unittest.main()
