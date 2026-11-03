"""Tests for src/special_days.py and the relaxed generated-line checks."""

import os
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dates import love_days
from deepseek_line import (
    GENERATED_LINE_MAX,
    build_love_line_prompt,
    generate_love_line,
    invalid_text_reason,
)
from special_days import get_special_day

TOGETHER = date(2026, 7, 8)
KNOWN = date(2019, 9, 2)


def special(today, next_meet=None):
    return get_special_day(today, TOGETHER, next_meet, KNOWN)


class SpecialDayTest(unittest.TestCase):
    def test_together_day_120(self):
        tier, fact = special(date(2026, 11, 4))
        self.assertEqual(tier, 3)
        self.assertIn("120", fact)

    def test_together_day_123_increasing_digits(self):
        tier, fact = special(date(2026, 11, 7))
        self.assertEqual(tier, 3)
        self.assertIn("123", fact)

    def test_valentine_day_also_together_day_222(self):
        self.assertEqual(love_days("2026-07-08", date(2027, 2, 14)), 222)
        tier, fact = special(date(2027, 2, 14))
        self.assertEqual(tier, 1)
        self.assertIn("Valentine", fact)

    def test_qixi(self):
        tier, fact = special(date(2027, 8, 8))
        self.assertEqual(tier, 1)
        self.assertIn("Qixi", fact)

    def test_ordinary_day_is_none(self):
        self.assertIsNone(special(date(2026, 11, 5)))

    def test_monthly_anniversary_on_the_8th(self):
        tier, fact = special(date(2026, 8, 8))
        self.assertEqual(tier, 1)
        self.assertIn("1 month", fact)

    def test_meeting_day_and_day_before(self):
        tier, fact = special(date(2026, 12, 20), date(2026, 12, 20))
        self.assertEqual(tier, 1)
        self.assertIn("today we meet", fact)
        tier, fact = special(date(2026, 12, 19), date(2026, 12, 20))
        self.assertEqual(tier, 1)
        self.assertIn("tomorrow we meet", fact)

    def test_missing_next_meet_skips_meeting_rules(self):
        self.assertIsNone(special(date(2026, 12, 19), None))

    def test_tier2_beats_tier3_on_day_100(self):
        tier, fact = special(date(2026, 10, 15))
        self.assertEqual(tier, 2)
        self.assertIn("100th", fact)

    def test_known_day_2626_abab(self):
        tier, fact = special(date(2026, 11, 9))
        self.assertEqual(tier, 3)
        self.assertIn("2626", fact)
        self.assertIn("ABAB", fact)

    def test_birthday_beats_tier2(self):
        tier, fact = special(date(2026, 8, 26))
        self.assertEqual(tier, 1)
        self.assertIn("Rachel", fact)


class RelaxedGeneratedValidationTest(unittest.TestCase):
    def test_short_poem_passes(self):
        self.assertIsNone(
            invalid_text_reason("The moon opens a door.\nThe mirror answers.\nTime walks on.")
        )

    def test_over_200_chars_is_rejected(self):
        self.assertEqual(invalid_text_reason("A" * 201 + "."), "too_long")
        self.assertEqual(
            invalid_text_reason("A" * (GENERATED_LINE_MAX - 1) + "."), None
        )

    def test_ellipsis_is_rejected(self):
        self.assertEqual(invalid_text_reason("The moon rises..."), "ellipsis")

    def test_five_lines_is_rejected(self):
        self.assertEqual(
            invalid_text_reason("One.\nTwo.\nThree.\nFour.\nFive."), "multiline"
        )

    def test_special_prompt_mentions_fact_and_relaxed_limits(self):
        prompt = build_love_line_prompt(
            daypart_a="morning",
            daypart_b="evening",
            weather_a="sunny",
            weather_b="clear",
            special_fact="today is Valentine's Day",
        )
        self.assertIn("Today is a special day: today is Valentine's Day", prompt)
        self.assertIn("Max 200", prompt)
        self.assertIn("2-4 lines", prompt)
        self.assertNotIn("Exactly one line", prompt)

    def test_special_poem_is_generated(self):
        poem = "The moon opens a door.\nThe mirror answers.\nTime walks on."
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"finish_reason": "stop", "message": {"content": poem}}]
        }
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            with mock.patch("deepseek_line.requests.post", return_value=response):
                line = generate_love_line(
                    theme=None,
                    time_a="07:00",
                    time_b="19:00",
                    weather_a="sunny",
                    weather_b="clear",
                    special_fact="today is Valentine's Day",
                )
        self.assertEqual(line, poem)


if __name__ == "__main__":
    unittest.main()
