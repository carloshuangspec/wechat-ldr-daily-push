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
        self.assertIn("emotionally intimate", prompt)
        self.assertIn("long-distance partner", prompt)
        self.assertIn("directly to you", prompt)
        self.assertIn("at most 20 printable ASCII characters", prompt)
        self.assertIn("Do not invent shared memories", prompt)
        self.assertIn("the other person's thoughts", prompt)
        self.assertNotIn("ordinary moments", prompt)
        self.assertNotIn("at most 16", prompt)

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
        cases = ((self.response(status=402), "http_402"),
                 (self.response(content="This line has far too many characters"), "invalid_text"),
                 (self.response(finish="length"), "abnormal_finish"))
        for response, category in cases:
            stderr = StringIO()
            with (
                self.subTest(category=category),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post", return_value=response),
                redirect_stderr(stderr),
            ):
                with self.assertRaises(DeepSeekLineError):
                    generate_love_line()
            self.assertEqual(stderr.getvalue(), f"line_failure={category}\n")

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
        self.assertEqual(stderr.getvalue(), "line_source=deepseek\n")

    def test_three_bad_texts_fail_without_a_fallback(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response(content="A" * 21)) as post,
            redirect_stderr(StringIO()) as stderr,
        ):
            with self.assertRaises(DeepSeekLineError):
                generate_love_line()
        self.assertEqual(post.call_count, 3)
        self.assertEqual(stderr.getvalue(), "line_failure=invalid_text\n")

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
