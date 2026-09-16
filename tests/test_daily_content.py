from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from daily_content import (  # noqa: E402
    DailyContentError,
    choose_line,
    parse_config,
    validate_inputs,
)


class ParseConfigTests(unittest.TestCase):
    def test_absent_or_blank_config_means_no_manual_content(self) -> None:
        for raw in (None, "", "  \t  "):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_config(raw))

    def test_theme_only_configuration(self) -> None:
        raw = json.dumps({"date": "2026-09-16", "theme": "A warm hello 💛"})
        self.assertEqual(
            parse_config(raw),
            {"date": "2026-09-16", "theme": "A warm hello 💛"},
        )

    def test_exact_and_theme_configuration_preserves_text(self) -> None:
        raw = json.dumps(
            {"date": "2026-09-16", "theme": "Morning", "exact": " Hi there! "}
        )
        self.assertEqual(
            parse_config(raw),
            {"date": "2026-09-16", "theme": "Morning", "exact": " Hi there! "},
        )

    def test_rejects_non_objects_invalid_json_and_duplicate_keys(self) -> None:
        for raw in (
            "not json",
            "null",
            "[]",
            '"text"',
            '{"date":"2026-09-16","date":"2026-09-17","theme":"Hi"}',
            '{"date":"2026-09-16","theme":"Hi","extra":{"x":1,"x":2}}',
        ):
            with self.subTest(raw=raw), self.assertRaises(DailyContentError):
                parse_config(raw)

    def test_rejects_unknown_fields_wrong_types_or_missing_content(self) -> None:
        invalid = (
            {"date": "2026-09-16"},
            {"date": "2026-09-16", "theme": "Hi", "unused": 1},
            {"date": 20260916, "theme": "Hi"},
            {"date": "2026-09-16", "theme": 1},
            {"date": "2026-09-16", "exact": False},
            {"date": "2026-09-16", "theme": ""},
            {"date": "2026-09-16", "exact": ""},
            {"date": "2026-09-16", "theme": "Hi", "exact": ""},
        )
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(DailyContentError):
                parse_config(json.dumps(config))

    def test_rejects_noncanonical_or_impossible_dates(self) -> None:
        for day in (
            "2026-9-16",
            "2026-09-16T00:00:00Z",
            "2026-02-29",
            "2026-13-01",
            "2026-09-16 ",
            "0000-01-01",
        ):
            with self.subTest(day=day), self.assertRaises(DailyContentError):
                parse_config(json.dumps({"date": day, "theme": "Hello"}))

    def test_accepts_real_leap_day(self) -> None:
        self.assertEqual(
            parse_config('{"date":"2028-02-29","exact":"Hello"}'),
            {"date": "2028-02-29", "exact": "Hello"},
        )

    def test_rejects_invalid_themes(self) -> None:
        for theme in ("", "   ", "\u3000", "x" * 121, "Line\nnext", "Line\rnext", "a\u2028b", "a\x00b", "a\x7fb"):
            with self.subTest(theme=repr(theme)), self.assertRaises(DailyContentError):
                parse_config(json.dumps({"date": "2026-09-16", "theme": theme}))

    def test_accepts_unicode_theme_at_character_limit(self) -> None:
        theme = "心" * 120
        self.assertEqual(
            parse_config(json.dumps({"date": "2026-09-16", "theme": theme})),
            {"date": "2026-09-16", "theme": theme},
        )

    def test_rejects_invalid_exact_lines_without_normalizing_them(self) -> None:
        for exact in (
            "",
            "   ",
            "A" * 21,
            "Hi\nthere",
            "Hi\rthere",
            "Hi\tthere",
            "Hi\x00there",
            "Hi\x7fthere",
            "你好",
            "Café",
        ):
            with self.subTest(exact=repr(exact)), self.assertRaises(DailyContentError):
                parse_config(json.dumps({"date": "2026-09-16", "exact": exact}))

    def test_accepts_printable_ascii_exact_at_limit(self) -> None:
        exact = "A" * 20
        self.assertEqual(
            parse_config(json.dumps({"date": "2026-09-16", "exact": exact})),
            {"date": "2026-09-16", "exact": exact},
        )

    def test_error_message_never_echoes_raw_config(self) -> None:
        marker = "NON_SECRET_TEST_MARKER"
        for raw in (marker, json.dumps({"date": "2026-09-16", "exact": marker})):
            with self.subTest(raw=raw), self.assertRaises(DailyContentError) as caught:
                parse_config(raw)
            self.assertEqual(str(caught.exception), "Invalid daily content configuration.")
            self.assertNotIn(marker, str(caught.exception))

    def test_malformed_or_duplicate_json_does_not_retain_raw_in_error_context(self) -> None:
        marker = "NON_SECRET_TEST_MARKER"
        malformed = '{"date":"2026-09-16","theme":"' + marker + '"'
        duplicate = (
            '{"date":"2026-09-16","theme":"'
            + marker
            + '","theme":"Hello"}'
        )
        for raw in (malformed, duplicate):
            with self.subTest(raw=raw), self.assertRaises(DailyContentError) as caught:
                parse_config(raw)
            self.assertIsNone(caught.exception.__context__)
            self.assertIsNone(caught.exception.__cause__)
            self.assertNotIn(marker, str(caught.exception))

    def test_invalid_calendar_date_does_not_retain_parser_error_context(self) -> None:
        with self.assertRaises(DailyContentError) as caught:
            parse_config('{"date":"2026-02-29","theme":"Hello"}')
        self.assertIsNone(caught.exception.__context__)


class ChooseLineTests(unittest.TestCase):
    def test_no_config_uses_generated_line(self) -> None:
        self.assertEqual(
            choose_line(None, date(2026, 9, 16)),
            (None, None, "generated", "none"),
        )

    def test_stale_config_uses_generated_line(self) -> None:
        self.assertEqual(
            choose_line({"date": "2026-09-15", "exact": "Hello"}, date(2026, 9, 16)),
            (None, None, "generated", "stale"),
        )

    def test_matching_shanghai_day_uses_exact_even_with_theme(self) -> None:
        config = {"date": "2026-09-17", "theme": "Sunny", "exact": "Good morning"}
        self.assertEqual(
            choose_line(config, date(2026, 9, 17)),
            ("Good morning", None, "manual", "active"),
        )
        self.assertEqual(
            choose_line(config, date(2026, 9, 16)),
            (None, None, "generated", "stale"),
        )

    def test_matching_shanghai_day_uses_theme_for_generation(self) -> None:
        self.assertEqual(
            choose_line({"date": "2026-09-16", "theme": "Sunny"}, date(2026, 9, 16)),
            (None, "Sunny", "generated", "active"),
        )

    def test_invalid_config_is_rejected_before_stale_check(self) -> None:
        with self.assertRaises(DailyContentError):
            choose_line({"date": "2026-09-15", "exact": "Hello\nthere"}, date(2026, 9, 16))


class ValidateInputsTests(unittest.TestCase):
    def test_editor_omits_absent_optional_values(self) -> None:
        self.assertEqual(
            validate_inputs("2026-09-16", "", "Hello"),
            {"date": "2026-09-16", "exact": "Hello"},
        )
        self.assertEqual(
            validate_inputs("2026-09-16", "Hello", None),
            {"date": "2026-09-16", "theme": "Hello"},
        )

    def test_editor_requires_a_valid_day_and_at_least_one_value(self) -> None:
        for values in (
            ("2026-09-16", None, ""),
            ("2026-9-16", "Hello", ""),
            (date(2026, 9, 16), "Hello", ""),
            ("2026-09-16", "Hello\nworld", ""),
            ("2026-09-16", "", "你好"),
        ):
            with self.subTest(values=values), self.assertRaises(DailyContentError):
                validate_inputs(*values)


if __name__ == "__main__":
    unittest.main()
