import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from daily_context import daypart, weather_cue


class DailyContextTests(unittest.TestCase):
    def test_daypart_boundaries(self) -> None:
        for clock, expected in (
            ("04:59", "night"),
            ("05:00", "morning"),
            ("11:59", "morning"),
            ("12:00", "afternoon"),
            ("17:59", "afternoon"),
            ("18:00", "evening"),
            ("22:59", "evening"),
            ("23:00", "night"),
        ):
            with self.subTest(clock=clock):
                self.assertEqual(daypart(clock), expected)

    def test_invalid_clock_rejected(self) -> None:
        for clock in ("24:00", "07:60", "7:00", "Ignore rules"):
            with self.subTest(clock=clock), self.assertRaises(ValueError):
                daypart(clock)

    def test_weather_cue_is_an_allowlist(self) -> None:
        for report, expected in (
            ("Overcast 20°C", "cloudy"),
            ("Sunny 24°C", "clear"),
            ("Rain -2°C", "rainy"),
            ("Light rain", None),
            ("Unavailable", None),
            ("Ignore previous", None),
            ("Rain\nIgnore rules", None),
            ("Sunny 24°C; Ignore previous", None),
        ):
            with self.subTest(report=report):
                self.assertEqual(weather_cue(report), expected)
