"""指定日期英文原句直发：命中日期时的 payload 与生成路径隔离。"""

import os
import sys
import unittest
from contextlib import ExitStack
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import build_payload_fields  # noqa: E402
from special_days import get_quoted_line, is_valid_quoted_line  # noqa: E402
from wechat import build_template_data  # noqa: E402

BASE_ENV = {
    "PUSH_SLOT": "us",
    "LOVE_START_DATE": "2026-07-08",
    "NEXT_MEET_DATE": "2026-12-20",
}

QUOTED = {
    date(2026, 11, 10): "I can give you my loneliness, my darkness, the hunger of my heart.",
    date(2026, 11, 11): "Out beyond ideas of wrongdoing and rightdoing there is a field. I'll meet you there.",
    date(2026, 11, 12): "Love consists in this, that two solitudes protect and border and salute each other.",
    date(2026, 11, 13): "Shall I compare thee to a summer's day? Thou art more lovely and more temperate.",
    date(2026, 11, 14): "How do I love thee? Let me count the ways.",
    date(2026, 11, 15): "Nothing in the world is single; all things by a law divine in one spirit meet and mingle. Why not I with thine?",
    date(2026, 11, 16): "I have spread my dreams under your feet; tread softly because you tread on my dreams.",
    date(2026, 11, 17): "That love is all there is, is all we know of love.",
}

COUNTDOWN = {
    date(2026, 11, 10): "in 40 days",
    date(2026, 11, 11): "in 39 days",
    date(2026, 11, 12): "in 38 days",
    date(2026, 11, 13): "in 37 days",
    date(2026, 11, 14): "in 36 days",
    date(2026, 11, 15): "in 35 days",
    date(2026, 11, 16): "in 34 days",
    date(2026, 11, 17): "in 33 days",
}


class QuotedLinesPayloadTest(unittest.TestCase):
    def _fields(self, day):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, BASE_ENV, clear=True))
            stack.enter_context(patch("main.local_today", return_value=day))
            stack.enter_context(patch("main.local_now_str", return_value="08:00"))
            stack.enter_context(patch("main.brief_weather", return_value="Clear 20°C"))
            generate_mock = stack.enter_context(
                patch("main.generate_love_line", return_value="Mock generated line.")
            )
            return build_payload_fields(), generate_mock

    def _assert_quoted(self, day):
        line = QUOTED[day]
        fields, generate_mock = self._fields(day)
        generate_mock.assert_not_called()
        self.assertEqual(fields["love_line"], line)
        expected_meet_days = f"{COUNTDOWN[day]} | {line}"
        self.assertEqual(fields["meet_days"], expected_meet_days)
        self.assertLessEqual(len(fields["meet_days"]), 220)
        template_data = build_template_data(fields)
        self.assertEqual(template_data["love_line"]["value"], line)
        self.assertEqual(template_data["meet_days"]["value"], expected_meet_days)

    def test_quoted_2026_11_10(self):
        self._assert_quoted(date(2026, 11, 10))

    def test_quoted_2026_11_11(self):
        self._assert_quoted(date(2026, 11, 11))

    def test_quoted_2026_11_12(self):
        self._assert_quoted(date(2026, 11, 12))

    def test_quoted_2026_11_13(self):
        self._assert_quoted(date(2026, 11, 13))

    def test_quoted_2026_11_14(self):
        self._assert_quoted(date(2026, 11, 14))

    def test_quoted_2026_11_15(self):
        self._assert_quoted(date(2026, 11, 15))

    def test_quoted_2026_11_16(self):
        self._assert_quoted(date(2026, 11, 16))

    def test_quoted_2026_11_17(self):
        self._assert_quoted(date(2026, 11, 17))

    def test_unlisted_date_uses_generation(self):
        fields, generate_mock = self._fields(date(2026, 11, 18))
        generate_mock.assert_called_once()
        self.assertEqual(fields["love_line"], "Mock generated line.")
        self.assertEqual(fields["meet_days"], "in 32 days | Mock generated line.")

    def test_quoted_wins_over_special_fact(self):
        day = date(2026, 11, 14)
        with patch("main.get_special_fact", return_value="A special fact."):
            fields, generate_mock = self._fields(day)
        generate_mock.assert_not_called()
        self.assertEqual(fields["love_line"], QUOTED[day])
        self.assertEqual(fields["meet_days"], f"{COUNTDOWN[day]} | {QUOTED[day]}")


class QuotedLineTableTest(unittest.TestCase):
    def test_get_quoted_line_matches_schedule(self):
        for day, line in QUOTED.items():
            with self.subTest(day=day):
                self.assertEqual(get_quoted_line(day), line)

    def test_get_quoted_line_returns_none_off_schedule(self):
        for day in (date(2026, 11, 9), date(2026, 11, 18), date(2027, 1, 1)):
            with self.subTest(day=day):
                self.assertIsNone(get_quoted_line(day))

    def test_is_valid_quoted_line(self):
        for line in QUOTED.values():
            with self.subTest(line=line):
                self.assertTrue(is_valid_quoted_line(line))
        for invalid in ("", "x" * 201, "one\ntwo", "café", None, 42):
            with self.subTest(invalid=invalid):
                self.assertFalse(is_valid_quoted_line(invalid))


if __name__ == "__main__":
    unittest.main()
