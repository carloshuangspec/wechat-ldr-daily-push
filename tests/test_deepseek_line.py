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

from daily_content import ENGLISH_LINE_MAX, contains_forbidden_note_label  # noqa: E402
from deepseek_line import (  # noqa: E402
    INVALID_TEXT_REASONS,
    MAX_ATTEMPTS,
    TARGET_LINE_LEN,
    DeepSeekLineError,
    build_love_line_prompt,
    invalid_text_reason,
    normalize_generated_line,
    daypart_from_hhmm,
    generate_love_line,
    sanitize_weather_fact,
)


class DeepSeekLineTests(unittest.TestCase):
    @staticmethod
    def response(content: object = "You are my home.", finish: object = "stop", status: int = 200) -> Mock:
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
            self.assertEqual(generate_love_line(), "You are my home.")
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
            self.assertEqual(generate_love_line(theme="ordinary days"), "You are my home.")
        self.assertIn("ordinary days", post.call_args.kwargs["json"]["messages"][0]["content"])
        self.assertNotIn("ordinary days", stderr.getvalue())

    def test_prompt_asks_for_dual_reader_line_without_inventing_details(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response(content="Still here with you.")) as post,
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(
                generate_love_line(
                    time_a="21:00",
                    time_b="09:00",
                    weather_a="Cloudy 20C",
                    weather_b="Fair 25C",
                ),
                "Still here with you.",
            )
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("both receive the same message", prompt)
        self.assertIn(f"Max {ENGLISH_LINE_MAX} printable ASCII characters", prompt)
        self.assertIn("Do not invent private memories", prompt)
        self.assertIn("girlfriend's feelings", prompt)
        self.assertIn("make her feel loved", prompt)
        self.assertIn("timezone handoff", prompt)
        self.assertIn("no-pressure ping", prompt)
        self.assertIn("side_a_daypart=evening", prompt)
        self.assertIn("side_b_daypart=morning", prompt)
        self.assertIn("side_a_weather=Cloudy 20C", prompt)
        self.assertIn("side_b_weather=Fair 25C", prompt)
        self.assertIn("romantic", prompt)
        self.assertIn("complete sentence", prompt)
        self.assertNotIn("Ann Arbor", prompt)
        self.assertNotIn("Shanghai", prompt)
        self.assertNotIn("at most 16", prompt)
        self.assertIn("OCCASIONAL only", prompt)
        self.assertIn("Note:", prompt)  # instruction forbids Note: label
        self.assertIn("fixed phrase library", prompt)

    def test_card_budget_and_incomplete_lines_fail_before_sending(self) -> None:
        self.assertEqual(ENGLISH_LINE_MAX, 48)
        for line in ("I miss you...", "I miss you and", "I miss you" + " so" * 18 + "."):
            with (
                self.subTest(line=line),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post", return_value=self.response(content=line)) as post,
                redirect_stderr(StringIO()),
            ):
                with self.assertRaises(DeepSeekLineError):
                    generate_love_line()
            self.assertEqual(post.call_count, 5)

    def test_daypart_and_weather_helpers(self) -> None:
        self.assertEqual(daypart_from_hhmm("09:00"), "morning")
        self.assertEqual(daypart_from_hhmm("15:30"), "afternoon")
        self.assertEqual(daypart_from_hhmm("21:00"), "evening")
        self.assertEqual(daypart_from_hhmm("23:10"), "night")
        self.assertIsNone(daypart_from_hhmm("bad"))
        self.assertEqual(sanitize_weather_fact("Cloudy 20°C"), "Cloudy 20C")
        self.assertIsNone(sanitize_weather_fact("Unavailable"))
        self.assertIsNone(sanitize_weather_fact("Weather offline"))
        prompt = build_love_line_prompt(
            daypart_a="morning",
            daypart_b="evening",
            weather_a="Clear 10C",
            weather_b=None,
        )
        self.assertIn("side_a_daypart=morning", prompt)
        self.assertIn("side_b_daypart=evening", prompt)
        self.assertIn("side_a_weather=Clear 10C", prompt)
        self.assertNotIn("side_b_weather=", prompt)

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
            "A" * (ENGLISH_LINE_MAX + 1),
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
            patch.object(requests, "post", return_value=self.response(content="  Hi there.  ")),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(generate_love_line(), "Hi there.")

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
                 (self.response(content="This letter line is intentionally way too long for the ASCII budget we enforce"),
                  "invalid_text reason=too_long"),
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
            self.assertEqual(stderr.getvalue().splitlines()[-1], f"line_failure={category}")

    def test_bad_first_text_is_regenerated_before_any_send(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", side_effect=[
                self.response(content="This letter is intentionally far too long for our ASCII budget and must be rejected"),
                self.response(content="Miss you today."),
            ]) as post,
            redirect_stderr(StringIO()) as stderr,
        ):
            self.assertEqual(generate_love_line(), "Miss you today.")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            stderr.getvalue(),
            "line_retry=1 category=invalid_text reason=too_long\nline_source=deepseek\n",
        )

    def test_five_bad_texts_fail_without_a_fallback(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response(content="A" * (ENGLISH_LINE_MAX + 1))) as post,
            redirect_stderr(StringIO()) as stderr,
        ):
            with self.assertRaises(DeepSeekLineError):
                generate_love_line()
        self.assertEqual(post.call_count, MAX_ATTEMPTS)
        self.assertEqual(MAX_ATTEMPTS, 5)
        self.assertEqual(
            stderr.getvalue(),
            "".join(f"line_retry={n} category=invalid_text reason=too_long\n" for n in range(1, 5))
            + "line_failure=invalid_text reason=too_long\n",
        )

    def test_http_error_is_not_regenerated(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response(status=402)) as post,
            redirect_stderr(StringIO()),
        ):
            with self.assertRaises(DeepSeekLineError):
                generate_love_line()
        post.assert_called_once()



    def test_literal_note_label_is_forbidden_case_insensitive(self) -> None:
        for line in (
            "Note: thinking of you",
            "Still here Note: always",
            "Miss you Note:",
            "NOTE: still here",
            "note: quiet sky",
            "nOtE: mixed case",
        ):
            with self.subTest(line_kind=line.split(":", 1)[0]):
                self.assertTrue(contains_forbidden_note_label(line))
                stderr = StringIO()
                with (
                    patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                    patch.object(requests, "post", return_value=self.response(content=line)) as post,
                    redirect_stderr(stderr),
                ):
                    with self.assertRaises(DeepSeekLineError) as caught:
                        generate_love_line(theme="ordinary days")
                self.assertEqual(str(caught.exception), "DeepSeek line unavailable")
                self.assertEqual(
                    stderr.getvalue(),
                    "".join(f"line_retry={n} category=forbidden_label\n" for n in range(1, 5))
                    + "line_failure=forbidden_label\n",
                )
                self.assertEqual(post.call_count, 5)
                leaked = stderr.getvalue() + str(caught.exception)
                self.assertNotIn("Note:", leaked)
                self.assertNotIn("NOTE:", leaked)
                self.assertNotIn("ordinary days", leaked)
                self.assertNotIn("TEST_KEY", leaked)
                self.assertNotIn(line, leaked)

    def test_clean_line_without_note_label_is_accepted(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(
                requests, "post", return_value=self.response(content="Sharing this quiet sky.")
            ),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(generate_love_line(), "Sharing this quiet sky.")

    def test_forbidden_label_is_regenerated_before_any_send(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(
                requests,
                "post",
                side_effect=[
                    self.response(content="Note: retry me"),
                    self.response(content="Miss you today."),
                ],
            ) as post,
            redirect_stderr(StringIO()) as stderr,
        ):
            self.assertEqual(generate_love_line(), "Miss you today.")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            stderr.getvalue(), "line_retry=1 category=forbidden_label\nline_source=deepseek\n"
        )
        self.assertNotIn("Note:", stderr.getvalue())

    def test_english_line_at_new_max_is_accepted(self) -> None:
        line = "A" * (ENGLISH_LINE_MAX - 1) + "."
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response(content=line)),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(generate_love_line(), line)

    # ---- Normalization (generated text only) ----

    def _generate(self, content: object) -> tuple[str, str]:
        stderr = StringIO()
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", return_value=self.response(content=content)),
            redirect_stderr(stderr),
        ):
            line = generate_love_line()
        return line, stderr.getvalue()

    def test_normalizes_surrounding_whitespace(self) -> None:
        line, log = self._generate("\n  Still choosing you.\t \n")
        self.assertEqual(line, "Still choosing you.")
        self.assertEqual(log, "line_normalized=outer_space\nline_source=deepseek\n")

    def test_normalizes_one_pair_of_wrapping_quotes_or_backticks(self) -> None:
        for wrapped in ('"Still choosing you."', "'Still choosing you.'", "`Still choosing you.`",
                        "\u201cStill choosing you.\u201d", "\u2018Still choosing you.\u2019",
                        '" Still choosing you. "'):
            with self.subTest(wrapped=repr(wrapped)):
                line, log = self._generate(wrapped)
                self.assertEqual(line, "Still choosing you.")
                self.assertIn("wrapping_quotes", log)
                self.assertNotIn("Still", log)

    def test_only_one_wrapping_pair_is_stripped(self) -> None:
        self.assertEqual(normalize_generated_line('""Hi you.""')[0], '"Hi you."')
        self.assertEqual(invalid_text_reason(normalize_generated_line('""Hi you.""')[0]), "quoted")
        # Mismatched wrappers are not stripped.
        self.assertEqual(normalize_generated_line("\"Hi you.'")[0], "\"Hi you.'")

    def test_normalizes_curly_apostrophes_and_quotes_to_ascii(self) -> None:
        line, log = self._generate("You\u2019re my \u201cfavorite\u201d hello.")
        self.assertEqual(line, 'You\'re my "favorite" hello.')
        self.assertEqual(log, "line_normalized=curly_quotes\nline_source=deepseek\n")

    def test_normalizes_em_and_en_dashes_to_hyphen(self) -> None:
        line, log = self._generate("Far apart\u2014still yours\u2013always.")
        self.assertEqual(line, "Far apart-still yours-always.")
        self.assertEqual(log, "line_normalized=dashes\nline_source=deepseek\n")

    def test_collapses_internal_horizontal_whitespace(self) -> None:
        line, log = self._generate("Still   here\twith  you.")
        self.assertEqual(line, "Still here with you.")
        self.assertEqual(log, "line_normalized=inner_space\nline_source=deepseek\n")

    def test_normalization_never_joins_lines_or_truncates(self) -> None:
        self.assertEqual(normalize_generated_line("Hi.\nYou.")[0], "Hi.\nYou.")
        long_text = "A" * (ENGLISH_LINE_MAX + 5) + "."
        self.assertEqual(normalize_generated_line(long_text)[0], long_text)
        self.assertEqual(invalid_text_reason(long_text), "too_long")

    def test_normalization_does_not_strip_or_rewrite_note_label(self) -> None:
        for raw in ("Note: miss you.", "\u201cNote: miss you.\u201d", "  note:  miss you.  ",
                    "Miss you\u2014Note: always."):
            with self.subTest(kind=raw[:6]):
                normalized, _ = normalize_generated_line(raw)
                self.assertTrue(contains_forbidden_note_label(normalized))
                self.assertEqual(invalid_text_reason(normalized), "forbidden_label")
                stderr = StringIO()
                with (
                    patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                    patch.object(requests, "post", return_value=self.response(content=raw)) as post,
                    redirect_stderr(stderr),
                ):
                    with self.assertRaises(DeepSeekLineError):
                        generate_love_line()
                self.assertEqual(post.call_count, 5)
                self.assertTrue(stderr.getvalue().endswith("line_failure=forbidden_label\n"))
                self.assertNotIn("miss you", stderr.getvalue().lower())

    def test_other_non_ascii_is_not_normalized(self) -> None:
        # Ellipsis char, NBSP-free non-ASCII letters and emoji stay rejected.
        for raw in ("Miss you\u2026", "Caf\u00e9 thoughts of you.", "Love you \u2764."):
            with self.subTest(raw=ascii(raw)):
                self.assertEqual(invalid_text_reason(normalize_generated_line(raw)[0]), "non_ascii")

    # ---- Diagnostic reasons ----

    def test_each_invalid_text_reason_is_classified(self) -> None:
        cases = {
            "": "empty",
            "   ": "empty",
            "Hi.\nYou.": "multiline",
            "Hi.\rYou.": "multiline",
            "Hi.\u2028You.": "multiline",
            "\u4f60\u5f88\u597d.": "non_ascii",
            "Hi\x07 you.": "non_printable",
            "A" * (ENGLISH_LINE_MAX + 1): "too_long",
            '""Hi you.""': "quoted",
            "`Hi you.": "quoted",
            "**Miss you.**": "markdown",
            "# Miss you": "markdown",
            "Miss you...": "ellipsis",
            "Miss you and": "no_end_punct",
            "Note: hi.": "forbidden_label",
        }
        for raw, reason in cases.items():
            with self.subTest(reason=reason):
                normalized, _ = normalize_generated_line(raw)
                self.assertEqual(invalid_text_reason(normalized), reason)
                if reason != "forbidden_label":
                    self.assertIn(reason, INVALID_TEXT_REASONS)
        self.assertIsNone(invalid_text_reason("Still here with you."))

    def test_final_invalid_text_log_has_reason_but_no_text(self) -> None:
        cases = {
            "Hi there.\nAnd again.": "multiline",
            "Caf\u00e9 SECRET_BODY you.": "non_ascii",
            "SECRET_BODY " * 6 + ".": "too_long",
            "``SECRET_BODY you.``": "quoted",
            "SECRET_BODY you and": "no_end_punct",
            "SECRET_BODY you...": "ellipsis",
            "  ": "empty",
        }
        for raw, reason in cases.items():
            stderr = StringIO()
            with (
                self.subTest(reason=reason),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post", return_value=self.response(content=raw)) as post,
                redirect_stderr(stderr),
            ):
                with self.assertRaises(DeepSeekLineError) as caught:
                    generate_love_line(theme="THEME_MARKER")
            log = stderr.getvalue()
            self.assertEqual(post.call_count, 5)
            self.assertEqual(log.splitlines()[-1], f"line_failure=invalid_text reason={reason}")
            leaked = log + str(caught.exception)
            for marker in ("SECRET_BODY", "THEME_MARKER", "TEST_KEY", "Caf", "Hi there"):
                self.assertNotIn(marker, leaked)
            for log_line in log.splitlines():
                self.assertRegex(
                    log_line,
                    r"\A(line_retry=[1-4] category=(invalid_text reason=[a-z_]+|forbidden_label)"
                    r"|line_failure=(invalid_text reason=[a-z_]+|forbidden_label))\Z",
                )

    # ---- Retry budget ----

    def test_success_on_fifth_attempt_after_mixed_content_rejections(self) -> None:
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
            patch.object(requests, "post", side_effect=[
                self.response(content="A" * 60 + "."),
                self.response(content="Note: hi."),
                self.response(content="Line one.\nLine two."),
                self.response(content="Miss you and"),
                self.response(content="Miss you today."),
            ]) as post,
            redirect_stderr(StringIO()) as stderr,
        ):
            self.assertEqual(generate_love_line(), "Miss you today.")
        self.assertEqual(post.call_count, 5)
        self.assertEqual(
            stderr.getvalue(),
            "line_retry=1 category=invalid_text reason=too_long\n"
            "line_retry=2 category=forbidden_label\n"
            "line_retry=3 category=invalid_text reason=multiline\n"
            "line_retry=4 category=invalid_text reason=no_end_punct\n"
            "line_source=deepseek\n",
        )

    def test_http_or_transport_error_after_bad_text_stops_immediately(self) -> None:
        for second, category in (
            (self.response(status=401), "http_401"),
            (self.response(status=429), "http_429"),
            (requests.ConnectionError("boom TEST_KEY"), "request_failed"),
            (self.response(finish="length"), "abnormal_finish"),
        ):
            with (
                self.subTest(category=category),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True),
                patch.object(requests, "post", side_effect=[
                    self.response(content="A" * 60 + "."), second, self.response(content="Hi you."),
                ]) as post,
                redirect_stderr(StringIO()) as stderr,
            ):
                with self.assertRaises(DeepSeekLineError):
                    generate_love_line()
            self.assertEqual(post.call_count, 2)
            self.assertEqual(stderr.getvalue().splitlines()[-1], f"line_failure={category}")
            self.assertNotIn("TEST_KEY", stderr.getvalue())

    def test_prompt_targets_short_plain_single_line(self) -> None:
        prompt = build_love_line_prompt()
        self.assertLess(TARGET_LINE_LEN, ENGLISH_LINE_MAX)
        self.assertIn(f"aim for {TARGET_LINE_LEN} characters or fewer", prompt)
        self.assertIn("plain ASCII apostrophe", prompt)
        self.assertIn("no curly quotes", prompt)
        self.assertIn("no em or en dashes", prompt)
        self.assertIn("no markdown", prompt)
        self.assertIn("No quotation marks or backticks", prompt)
        self.assertIn("Exactly one line", prompt)
        self.assertIn("Note:", prompt)



if __name__ == "__main__":
    unittest.main()
