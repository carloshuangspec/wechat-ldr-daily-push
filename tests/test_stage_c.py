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
import gemini_line  # noqa: E402
import main  # noqa: E402
import weather  # noqa: E402
import wechat  # noqa: E402


LIVE_GITHUB_ENV = {
    "LIVE_CONFIRMATION": "SEND_CN_ONCE",
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_ACTOR": "carloshuangspec",
    "GITHUB_TRIGGERING_ACTOR": "carloshuangspec",
    "GITHUB_RUN_ATTEMPT": "1",
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
            patch.object(main, "build_payload_fields", return_value={}),
            patch.object(main, "send_template") as send,
            redirect_stdout(stdout),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main.main(), 0)
            send.assert_not_called()
            self.assertNotIn("TEST_TEMPLATE_ID_DO_NOT_LOG", stdout.getvalue())
            self.assertNotIn("TEST_OPENID_DO_NOT_LOG", stdout.getvalue())
            self.assertFalse(json.loads(stdout.getvalue())["meta"]["gemini_key_set"])

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

    def test_local_live_cn_is_rejected(self) -> None:
        with patch.dict(
            os.environ, {"LIVE_CONFIRMATION": "SEND_CN_ONCE"}, clear=True
        ):
            with self.assertRaises(main.ConfigError):
                main.validate_send_context("live", "cn")

    def test_actions_schedule_cannot_become_live_cn(self) -> None:
        with patch.dict(
            os.environ,
            {
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
                    "WECHAT_OPENID": generic_openid,
                },
                clear=True,
            ),
            patch.object(main, "build_payload_fields", return_value={}),
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
                "TEST_SECRET_DO_NOT_LOG",
                "TEST_TEMPLATE_DO_NOT_LOG",
            ):
                self.assertNotIn(sentinel, stdout.getvalue())


class DateTests(unittest.TestCase):
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
                self.assertEqual(fields["meet_days"], meet_text)
                self.assertTrue(
                    all(value.replace("°", "").isascii() for value in fields.values())
                )

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


class LoveLineTests(unittest.TestCase):
    def test_static_fallback_is_english_and_fits_template(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(gemini_line.FALLBACK_LINES)
            self.assertTrue(
                all(line.isascii() and len(line) <= 20 for line in gemini_line.FALLBACK_LINES)
            )
            self.assertIn(gemini_line.generate_love_line(), gemini_line.FALLBACK_LINES)

    def test_gemini_uses_an_english_prompt_and_short_english_result(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "You are my home"}]}}]
        }
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=response) as post,
        ):
            self.assertEqual(gemini_line.generate_love_line(), "You are my home")
            prompt = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
            self.assertIn("English only", prompt)

    def test_gemini_non_english_or_too_long_uses_english_fallback(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        for generated in ("早安，想你了", "Missing you across all the miles between us"):
            response.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": generated}]}}]
            }
            with (
                self.subTest(generated=generated),
                patch.dict(os.environ, {"GEMINI_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post", return_value=response),
            ):
                self.assertIn(gemini_line.generate_love_line(), gemini_line.FALLBACK_LINES)

    def test_malformed_gemini_responses_use_english_fallback(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        bodies = (
            [],
            {"candidates": "not-a-list"},
            {"candidates": [{"content": {"parts": [123]}}]},
            {"candidates": [{"content": {"parts": [{"text": 123}]}}]},
        )
        for body in bodies:
            response.json.return_value = body
            with (
                self.subTest(body=body),
                patch.dict(os.environ, {"GEMINI_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post", return_value=response),
            ):
                try:
                    line = gemini_line.generate_love_line()
                except (AttributeError, TypeError) as exc:
                    self.fail(f"Malformed response escaped as {type(exc).__name__}")
                self.assertIn(line, gemini_line.FALLBACK_LINES)


class WeChatSafetyTests(unittest.TestCase):
    @staticmethod
    def response(data: object) -> Mock:
        response = Mock()
        response.json.return_value = data
        response.raise_for_status.return_value = None
        return response

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
            patch.object(main, "build_payload_fields", return_value={}),
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
            patch.object(main, "build_payload_fields", return_value={}),
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

    def test_weather_now_key_uses_header_not_query(self) -> None:
        response = Mock()
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


    def test_missing_host_degrades_without_request(self) -> None:
        with patch.dict(
            os.environ, {"QWEATHER_KEY": "TEST_QWEATHER_KEY"}, clear=True
        ), patch.object(weather.requests, "get") as request:
            self.assertEqual(weather.brief_weather("Shanghai"), weather.UNAVAILABLE_CONFIG)
            request.assert_not_called()

    def test_missing_key_degrades_without_request(self) -> None:
        with patch.dict(
            os.environ,
            {"QWEATHER_API_HOST": "https://abc123.qweatherapi.com"},
            clear=True,
        ), patch.object(weather.requests, "get") as request:
            self.assertEqual(weather.brief_weather("Shanghai"), weather.UNAVAILABLE_CONFIG)
            request.assert_not_called()

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
            ), patch.object(weather.requests, "get") as request:
                self.assertEqual(
                    weather.brief_weather("Shanghai"), weather.UNAVAILABLE_CONFIG
                )
                request.assert_not_called()

    def test_template_contains_qweather_attribution(self) -> None:
        data = wechat.build_template_data(
            {"weather_source": "QWeather https://www.qweather.com"}
        )
        self.assertEqual(
            data["weather_source"]["value"],
            "QWeather https://www.qweather.com",
        )


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
        self.assertIn('cron: "7 8 * * *"', self.workflow)
        self.assertIn('timezone: "Asia/Shanghai"', self.workflow)
        self.assertIn("github.event.schedule == '7 8 * * *'", self.workflow)
        self.assertIn('cron: "13 8 * * *"', self.workflow)
        self.assertIn('timezone: "America/Detroit"', self.workflow)
        self.assertIn("github.event.schedule == '13 8 * * *'", self.workflow)

    def test_stage_c_manual_gate_is_exact(self) -> None:
        self.assertIn('[ "$REQUEST_SLOT" != "cn" ]', self.workflow)
        self.assertIn(
            '[ "$REQUEST_CONFIRMATION" != "SEND_CN_ONCE" ]', self.workflow
        )
        self.assertIn('REQUEST_REF: ${{ github.ref }}', self.workflow)
        self.assertIn('REQUEST_ATTEMPT: ${{ github.run_attempt }}', self.workflow)
        self.assertIn('github.ref == \'refs/heads/main\'', self.workflow)
        self.assertIn("github.run_attempt == '1'", self.workflow)

    def test_preview_jobs_have_no_wechat_credentials(self) -> None:
        cn_job = self.workflow.split("  preview-cn:", 1)[1].split(
            "  preview-us:", 1
        )[0]
        us_job = self.workflow.split("  preview-us:", 1)[1].split(
            "  live-cn:", 1
        )[0]
        for job in (cn_job, us_job):
            self.assertIn("SEND_MODE: dry-run", job)
            self.assertNotIn("WECHAT_APP_ID:", job)
            self.assertNotIn("WECHAT_APP_SECRET:", job)
            self.assertNotIn("WECHAT_TEMPLATE_ID:", job)
            self.assertNotIn("WECHAT_OPENID_CN:", job)
            self.assertNotIn("SEND_MODE: ${{", job)

    def test_optional_gemini_is_available_in_each_message_job(self) -> None:
        self.assertEqual(self.workflow.count("GEMINI_API_KEY:"), 3)
        self.assertEqual(self.workflow.count("GEMINI_MODEL:"), 3)

    def test_only_live_cn_job_can_load_wechat_credentials(self) -> None:
        live_job = self.workflow.split("  live-cn:", 1)[1]
        self.assertIn("SEND_MODE: live", live_job)
        self.assertIn("LIVE_CONFIRMATION: ${{ inputs.confirmation }}", live_job)
        self.assertIn("WECHAT_APP_SECRET: ${{ secrets.WECHAT_APP_SECRET }}", live_job)
        self.assertIn("WECHAT_OPENID_CN: ${{ secrets.WECHAT_OPENID_CN }}", live_job)
        self.assertEqual(self.workflow.count("WECHAT_APP_SECRET:"), 1)
        self.assertEqual(self.workflow.count("WECHAT_OPENID_CN:"), 1)
        self.assertNotIn("WECHAT_OPENID_US:", self.workflow)
        self.assertEqual(self.workflow.count("SEND_MODE: live"), 1)
        self.assertNotIn("DRY_RUN:", self.workflow)
        self.assertNotIn("vars.DRY_RUN", self.workflow)

    def test_workflow_uses_current_node24_actions_and_fixed_concurrency(self) -> None:
        self.assertEqual(self.workflow.count("actions/checkout@v7"), 3)
        self.assertEqual(self.workflow.count("actions/setup-python@v7"), 3)
        self.assertIn("group: wechat-ldr-daily-push-stage-c", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)


if __name__ == "__main__":
    unittest.main()
