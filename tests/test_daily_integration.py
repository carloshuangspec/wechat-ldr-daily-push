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
        self.assertEqual(fields["meet_days"], "in 95 days | I ache for you.")
        self.assertEqual(
            wechat.build_template_data(fields)["meet_days"]["value"],
            "in 95 days | I ache for you.",
        )
        self.assertEqual(fields["love_line"], "I ache for you.")
        self.assertTrue(fields["greeting"].startswith("Known: ≈"))

    def test_long_love_line_shows_first_line_in_meeting_field(self) -> None:
        line = "I love the ordinary hours we get to build together, one by one."
        with (
            patch.dict(os.environ, {**BASE_ENV, "PUSH_SLOT": "us"}, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value=line),
        ):
            fields = main.build_payload_fields()
        self.assertEqual(
            fields["meet_days"],
            "in 95 days | I love the ordinary hours we get to build together,",
        )
        self.assertEqual(fields["love_line"], line)
        self.assertEqual(
            wechat.build_template_data(fields)["love_line"]["value"], line
        )
        self.assertEqual(
            wechat.build_template_data(fields)["meet_days"]["value"],
            "in 95 days | I love the ordinary hours we get to build together,",
        )

    def test_special_day_poem_first_line_is_visible_on_card(self) -> None:
        poem = (
            "One two three, the days line up in a row.\n"
            "I count them aloud and they answer your name.\n"
            "Tomorrow will be four, and still I choose you."
        )
        with (
            patch.dict(os.environ, {**BASE_ENV, "PUSH_SLOT": "us"}, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 11, 7)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value=poem) as generate,
        ):
            fields = main.build_payload_fields()
        self.assertIsNotNone(generate.call_args.kwargs["special_fact"])
        self.assertEqual(fields["love_days"], "123 days")
        self.assertEqual(fields["love_line"], poem)
        self.assertEqual(
            fields["meet_days"],
            "in 43 days | One two three, the days line up in a row.",
        )
        self.assertEqual(
            wechat.build_template_data(fields)["meet_days"]["value"],
            "in 43 days | One two three, the days line up in a row.",
        )
        self.assertEqual(
            wechat.build_template_data(fields)["love_line"]["value"], poem
        )

    def test_special_day_long_first_line_is_cut_at_word_boundary(self) -> None:
        poem = (
            "When I wake, the first thing I remember is the sound of your voice calling me home.\n"
            "The mirror of time returns your face.\n"
            "I choose you again."
        )
        with (
            patch.dict(os.environ, {**BASE_ENV, "PUSH_SLOT": "us"}, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 11, 8)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value=poem) as generate,
        ):
            fields = main.build_payload_fields()
        self.assertIsNotNone(generate.call_args.kwargs["special_fact"])
        self.assertEqual(fields["love_days"], "124 days")
        self.assertEqual(fields["love_line"], poem)
        self.assertEqual(
            fields["meet_days"],
            "in 42 days | When I wake, the first thing I remember is the",
        )
        self.assertLessEqual(len(fields["meet_days"]), 64)
        self.assertEqual(
            wechat.build_template_data(fields)["meet_days"]["value"],
            "in 42 days | When I wake, the first thing I remember is the",
        )

    def test_card_first_line_cuts_at_word_boundary(self) -> None:
        self.assertEqual(main._card_first_line("Short line.", 50), "Short line.")
        self.assertEqual(
            main._card_first_line("First line here.\nSecond line.", 50),
            "First line here.",
        )
        self.assertEqual(
            main._card_first_line(
                "When I wake, the first thing I remember is the sound of your voice.",
                50,
            ),
            "When I wake, the first thing I remember is the",
        )
        self.assertEqual(main._card_first_line("One two three.", 0), "")
        self.assertEqual(main._card_first_line("", 50), "")

    def test_manual_exact_too_long_for_card_is_rejected(self) -> None:
        line = (
            "Good morning. I love waking up as yours. "
            "I miss you, and I am waiting for you."
        )
        env = {
            **BASE_ENV,
            "DAILY_MESSAGE_CONFIG": (
                "mode=cn; "
                "date=2026-09-16; "
                "theme=ordinary days; "
                f"line={line}"
            ),
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line") as generate,
        ):
            with self.assertRaises(main.ConfigError):
                main.build_payload_fields()
        generate.assert_not_called()

    def test_visible_mirror_skips_manual_padding_but_keeps_exact(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    **BASE_ENV,
                    "DAILY_MESSAGE_CONFIG": (
                        "mode=cn; date=2026-09-16; theme=ordinary days; "
                        "line=  Good morning, my love.  "
                    ),
                },
                clear=True,
            ),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line") as generate,
        ):
            fields = main.build_payload_fields()
        generate.assert_not_called()
        self.assertEqual(
            fields["meet_days"], "in 95 days | Good morning, my love."
        )
        self.assertEqual(
            wechat.build_template_data(fields)["meet_days"]["value"],
            "in 95 days | Good morning, my love.",
        )

    def test_meeting_field_rejects_truncation_of_emotional_line(self) -> None:
        long_line = "A" * 65
        fields = {"meet_days": "in 3 days | " + long_line, "love_line": "A"}
        with self.assertRaises(ValueError):
            wechat.build_template_data(fields)

    def test_exact_cn_line_uses_chosen_theme(self) -> None:
        with (
            patch.dict(os.environ, {**BASE_ENV, "PUSH_SLOT": "us"}, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Hold on, my love."),
            patch.object(main, "parse_config", return_value=None),
            patch.object(main, "choose_line", return_value=("Exact line", "chosen theme", None, "none")),
            patch.object(main, "get_special_fact", return_value=None) as special,
        ):
            fields = main.build_payload_fields()
        self.assertEqual(fields["love_line"], "Exact line")
        self.assertEqual(fields["meet_days"], "in 95 days | Exact line")
        self.assertEqual(
            wechat.build_template_data(fields)["meet_days"]["value"],
            "in 95 days | Exact line",
        )
        special.assert_not_called()

    def test_matching_theme_guides_one_api_call(self) -> None:
        env = {
            **BASE_ENV,
            "DAILY_MESSAGE_CONFIG": (
                "mode=cn; date=2026-09-16; theme=ordinary days; "
                "line=Hold on, my love."
            ),
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Hold on.") as generate,
        ):
            main.build_payload_fields()
        generate.assert_called_once_with(
            theme="ordinary days",
            time_a="08:00",
            time_b="08:00",
            weather_a="Clear 20°C",
            weather_b="Clear 20°C",
            special_fact=None,
        )

    def test_stale_cn_config_is_ignored(self) -> None:
        env = {
            **BASE_ENV,
            "DAILY_MESSAGE_CONFIG": "mode=cn; date=2026-01-01; line=Stale line.",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Here with you.") as generate,
        ):
            fields = main.build_payload_fields()
        generate.assert_called_once()
        self.assertEqual(
            generate.call_args.kwargs["special_fact"],
            None,
        )
        self.assertEqual(fields["love_line"], "Here with you.")

    def test_us_ignores_even_malformed_cn_config(self) -> None:
        env = {
            **BASE_ENV,
            "PUSH_SLOT": "us",
            "DAILY_MESSAGE_CONFIG": "garbage=1; broken",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Here with you.") as generate,
        ):
            main.build_payload_fields()
        self.assertIsNone(generate.call_args.kwargs["special_fact"])
        generate.assert_called_once_with(
            theme=None,
            time_a="08:00",
            time_b="08:00",
            weather_a="Clear 20°C",
            weather_b="Clear 20°C",
            special_fact=None,
        )

    def test_bad_cn_config_is_recorded_and_falls_back_to_source_text(self) -> None:
        env = {
            **BASE_ENV,
            "DAILY_MESSAGE_CONFIG": "mode=cn; date=2026-09-16; line=Hi. Their line.",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Here with you.") as generate,
        ):
            with StringIO() as sink:
                with redirect_stderr(sink):
                    main.build_payload_fields()
                captured = sink.getvalue()
        self.assertNotIn("line_source=deepseek", captured)
        generate.assert_called_once_with(
            theme=None,
            time_a="08:00",
            time_b="08:00",
            weather_a="Clear 20°C",
            weather_b="Clear 20°C",
            special_fact=None,
        )

    def test_template_rejects_long_love_line_without_ellipsis(self) -> None:
        long_line = "A" * 65
        fields = {"meet_days": "in 3 days", "love_line": long_line}
        with self.assertRaises(ValueError):
            wechat.build_template_data(fields)

    def test_render_failure_cannot_send_or_leak_line(self) -> None:
        fields = {"love_line": "X" * 65}
        with patch.object(main, "build_payload_fields", return_value=fields), patch.object(
            main, "build_template_data", side_effect=ValueError("template field too long")
        ), patch.object(main, "send_template") as send:
            with StringIO() as sink:
                with redirect_stderr(sink):
                    self.assertEqual(main.main(), 1)
                self.assertNotIn("X" * 65, sink.getvalue())
        send.assert_not_called()

    def test_preview_reports_only_fixed_metadata_not_theme(self) -> None:
        """The logged date and override status must never claim a theme."""
        env = {
            **BASE_ENV,
            "DAILY_MESSAGE_CONFIG": (
                "mode=cn; date=2026-09-16; theme=ordinary days; "
                "line=Good morning, my love."
            ),
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=date(2026, 9, 16)),
            patch.object(main, "local_now_str", return_value="08:00"),
            patch.object(main, "brief_weather", return_value="Clear 20°C"),
            patch.object(main, "generate_love_line", return_value="Generated, not used."),
            patch.object(main, "send_template") as send,
            patch.object(main, "validate_live_configuration", return_value=[]),
        ):
            with StringIO() as sink:
                with redirect_stderr(sink):
                    self.assertEqual(main.main(), 0)
                captured = sink.getvalue()
        self.assertNotIn("ordinary days", captured)
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
