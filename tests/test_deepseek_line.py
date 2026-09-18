from __future__ import annotations

import os
import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deepseek_line import DeepSeekLineError, generate_love_line  # noqa: E402


class DeepSeekLineTests(unittest.TestCase):
    @staticmethod
    def response(content: object = "You are my home", finish: object = "stop", status: int = 200) -> Mock:
        r = Mock()
        r.status_code = status
        r.json.return_value = {
            "choices": [{"finish_reason": finish, "message": {"content": content}}]
        }
        return r

    def test_missing_key_never_makes_request_or_returns_fallback(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(requests, "post") as post:
            with self.assertRaises(DeepSeekLineError):
                generate_love_line()
        post.assert_not_called()

    def test_valid_response_uses_official_endpoint_and_header_only_key(self) -> None:
        stderr = StringIO()
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response()) as post,
            redirect_stderr(stderr),
        ):
            self.assertEqual(generate_love_line(), "You are my home")
        self.assertEqual(stderr.getvalue(), "line_source=deepseek\n")
        self.assertEqual(post.call_args.args[0], "https://api.deepseek.com/chat/completions")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer TEST_KEY")
        self.assertNotIn("TEST_KEY", str(kwargs["json"]))
        self.assertNotIn("params", kwargs)
        self.assertIs(kwargs["allow_redirects"], False)
        self.assertEqual(kwargs["json"]["model"], "deepseek-flash")
        self.assertEqual(kwargs["json"]["thinking"], {"type": "disabled"})
        self.assertIs(kwargs["json"]["stream"], False)
        self.assertIn("English", kwargs["json"]["messages"][0]["content"])

    def test_theme_is_in_prompt_but_not_log(self) -> None:
        stderr = StringIO()
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response()) as post,
            redirect_stderr(stderr),
        ):
            self.assertEqual(generate_love_line(theme="ordinary days"), "You are my home")
        self.assertIn("ordinary days", post.call_args.kwargs["json"]["messages"][0]["content"])
        self.assertNotIn("ordinary days", stderr.getvalue())

    def test_prompt_asks_for_a_tender_personal_line_without_inventing_details(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response(content="I choose you, always")) as post,
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(generate_love_line(), "I choose you, always")
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("one original emotionally warm English line", prompt)
        self.assertIn("both recipients receive", prompt)
        self.assertIn("cross-time-zone handoff", prompt)
        self.assertIn("low-pressure thought", prompt)
        self.assertIn("real weather detail", prompt)
        self.assertIn("gentle distance humor", prompt)
        self.assertIn("occasional optional question", prompt)
        self.assertIn("no reply", prompt)
        self.assertIn("natural", prompt)
        self.assertIn("at most 20 printable ASCII characters", prompt)
        self.assertIn("no quotes, emoji, or line breaks", prompt)
        self.assertIn("Do not invent memories, events, places, or feelings", prompt)

    def test_default_prompt_uses_only_anonymous_normalized_context(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response()) as post,
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(
                generate_love_line(dayparts=("morning", "evening"), weather=("cloudy", "clear")),
                "You are my home",
            )
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("both recipients receive", prompt)
        self.assertIn("morning", prompt)
        self.assertIn("evening", prompt)
        self.assertIn("cloudy", prompt)
        self.assertIn("clear", prompt)
        self.assertIn("optional", prompt)
        self.assertNotIn("city", prompt.lower())
        self.assertNotIn("temperature", prompt.lower())
        self.assertNotIn("provider", prompt.lower())
        self.assertNotIn("TEST_KEY", prompt)

    def test_absent_weather_does_not_supply_a_weather_fact(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response()) as post,
            redirect_stderr(StringIO()),
        ):
            generate_love_line(dayparts=("night", "afternoon"), weather=(None, None))
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertNotIn("weather cues:", prompt)
        self.assertIn("night", prompt)
        self.assertIn("afternoon", prompt)

    def test_partial_weather_supplies_only_the_known_cue(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response()) as post,
            redirect_stderr(StringIO()),
        ):
            generate_love_line(weather=(None, "rainy"))
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("second recipient: rainy", prompt)
        self.assertNotIn("first recipient:", prompt)
        self.assertNotIn("morning", prompt)

    def test_manual_theme_replaces_default_angles_and_omits_context(self) -> None:
        stderr = StringIO()
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response()) as post,
            redirect_stderr(stderr),
        ):
            generate_love_line(
                theme="ordinary days",
                dayparts=("morning", "evening"),
                weather=("cloudy", "clear"),
            )
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("ordinary days", prompt)
        self.assertIn("both recipients receive", prompt)
        self.assertIn("Do not invent memories, events, places, or feelings", prompt)
        self.assertIn("at most 20 printable ASCII characters", prompt)
        for default_only in (
            "cross-time-zone handoff", "low-pressure thought", "real weather detail",
            "gentle distance humor", "occasional optional question",
            "morning", "evening", "cloudy", "clear",
        ):
            with self.subTest(default_only=default_only):
                self.assertNotIn(default_only, prompt)
        self.assertEqual(stderr.getvalue(), "line_source=deepseek\n")

    def test_manual_theme_ignores_malformed_context_entirely(self) -> None:
        for context in (
            {"dayparts": ("morning", ["UNTRUSTED_CLOCK"])},
            {"weather": ("UNTRUSTED_WEATHER", {"raw": "private"})},
        ):
            with self.subTest(context=context):
                stderr = StringIO()
                with (
                    patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                    patch.object(requests, "post", return_value=self.response()) as post,
                    redirect_stderr(stderr),
                ):
                    line = generate_love_line(theme="ordinary days", **context)
                self.assertEqual(line, "You are my home")
                post.assert_called_once()
                prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
                self.assertIn("ordinary days", prompt)
                self.assertNotIn("cross-time-zone handoff", prompt)
                self.assertNotIn("Anonymous dayparts", prompt)
                self.assertNotIn("Anonymous weather cues", prompt)
                self.assertNotIn("UNTRUSTED", prompt)
                self.assertEqual(stderr.getvalue(), "line_source=deepseek\n")

    def test_malformed_context_is_rejected_before_request_with_fixed_diagnostic(self) -> None:
        invalid_contexts = (
            {"dayparts": "morning"},
            {"dayparts": ["morning", "evening"]},
            {"dayparts": ("morning",)},
            {"dayparts": ("morning", "evening", "night")},
            {"dayparts": ("morning", ["evening"])},
            {"dayparts": ("morning", "05:00 private place")},
            {"dayparts": (None, "evening")},
            {"weather": ["clear", "cloudy"]},
            {"weather": ("clear",)},
            {"weather": ("clear", "cloudy", None)},
            {"weather": ("clear", {"private": "value"})},
            {"weather": ("Cloudy 25°C private place", "clear")},
            {"weather": ("snow", None)},
            {"weather": (42, "clear")},
        )
        for context in invalid_contexts:
            with self.subTest(context=context):
                stderr = StringIO()
                with (
                    patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                    patch.object(requests, "post") as post,
                    redirect_stderr(stderr),
                ):
                    with self.assertRaises(DeepSeekLineError) as caught:
                        generate_love_line(**context)
                post.assert_not_called()
                self.assertEqual(str(caught.exception), "DeepSeek line unavailable")
                self.assertEqual(stderr.getvalue(), "line_failure=invalid_context\n")

    def test_bad_theme_fails_before_request(self) -> None:
        for theme in ("  ", "a\nb", "x" * 121):
            with (
                self.subTest(theme=repr(theme)),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post") as post,
            ):
                with self.assertRaises(DeepSeekLineError):
                    generate_love_line(theme=theme)
                post.assert_not_called()

    def test_invalid_completion_is_rejected_in_full(self) -> None:
        for text in (
            "",
            " ",
            "Hi\nAgain",
            "Hi\rAgain",
            '"Hello"',
            "'Hello'",
            "你很好",
            "A" * 21,
            123,
            "Hi\tthere",
        ):
            with (
                self.subTest(text=repr(text)),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post", return_value=self.response(content=text)),
            ):
                with self.assertRaises(DeepSeekLineError):
                    generate_love_line()

    def test_only_outer_ascii_spaces_are_removed(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response(content="  Hi there  ")),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(generate_love_line(), "Hi there")

    def test_abnormal_finish_or_http_status_fails_closed(self) -> None:
        for finish, status in (("length", 200), (None, 200), ("stop", 301), ("stop", 401), ("stop", 503)):
            with (
                self.subTest(finish=finish, status=status),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post", return_value=self.response(finish=finish, status=status)),
            ):
                with self.assertRaises(DeepSeekLineError):
                    generate_love_line()

    def test_malformed_json_or_multiple_choices_fails_closed(self) -> None:
        for data in ([], {}, {"choices": []}, {"choices": "bad"},
                     {"choices": [{"finish_reason": "stop", "message": {"content": "Hi"}},
                                  {"finish_reason": "stop", "message": {"content": "Bye"}}]},
                     {"choices": [{"finish_reason": "stop", "message": {"content": None}}]}):
            response = self.response()
            response.json.return_value = data
            with (
                self.subTest(data=data),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post", return_value=response),
            ):
                with self.assertRaises(DeepSeekLineError):
                    generate_love_line()

    def test_network_exception_error_message_is_fixed_and_no_key_leaks(self) -> None:
        stderr = StringIO()
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", side_effect=requests.Timeout("SECRET TEST_KEY RAW_BODY")),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(DeepSeekLineError) as caught:
                generate_love_line()
        self.assertEqual(str(caught.exception), "DeepSeek line unavailable")
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(stderr.getvalue(), "line_failure=request_failed\n")

    def test_failure_diagnostics_are_fixed_categories_only(self) -> None:
        cases = ((self.response(status=402), "http_402", ""),
                 (self.response(content="This line has far too many characters"),
                  "invalid_text", "line_reject=too_long\n" * 3),
                 (self.response(finish="length"), "abnormal_finish", ""))
        for response, category, rejections in cases:
            stderr = StringIO()
            with (
                self.subTest(category=category),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post", return_value=response),
                redirect_stderr(stderr),
            ):
                with self.assertRaises(DeepSeekLineError):
                    generate_love_line()
            self.assertEqual(stderr.getvalue(), f"{rejections}line_failure={category}\n")

    def test_bad_first_text_is_regenerated_before_any_send(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", side_effect=[
                self.response(content="This is much too long for the short line"),
                self.response(content="Miss you today"),
            ]) as post,
            redirect_stderr(StringIO()) as stderr,
        ):
            self.assertEqual(generate_love_line(), "Miss you today")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(stderr.getvalue(), "line_reject=too_long\nline_source=deepseek\n")

    def test_three_bad_texts_fail_without_a_fallback(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response(content="A" * 21)) as post,
            redirect_stderr(StringIO()) as stderr,
        ):
            with self.assertRaises(DeepSeekLineError):
                generate_love_line()
        self.assertEqual(post.call_count, 3)
        self.assertEqual(
            stderr.getvalue(), "line_reject=too_long\n" * 3 + "line_failure=invalid_text\n"
        )

    def test_invalid_text_reports_fixed_rejection_reasons_without_body(self) -> None:
        stderr = StringIO()
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", side_effect=[
                self.response(content='"A very long SECRET_BODY ☀"'),
                self.response(content="Hello\nworld"),
                self.response(content='"Hello"'),
            ]) as post,
            redirect_stderr(stderr),
        ):
            with self.assertRaises(DeepSeekLineError):
                generate_love_line()
        self.assertEqual(post.call_count, 3)
        self.assertEqual(
            stderr.getvalue(),
            "line_reject=too_long,non_ascii,quoted\n"
            "line_reject=non_printable\n"
            "line_reject=quoted\n"
            "line_failure=invalid_text\n",
        )
        self.assertNotIn("SECRET_BODY", stderr.getvalue())

    def test_http_error_is_not_regenerated(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response(status=402)) as post,
            redirect_stderr(StringIO()),
        ):
            with self.assertRaises(DeepSeekLineError):
                generate_love_line()
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
