from __future__ import annotations

import json
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import edit_daily_message as editor  # noqa: E402


class DailyEditorTests(unittest.TestCase):
    @staticmethod
    def answers(*values: str):
        return patch("builtins.input", side_effect=values)

    def test_default_day_is_in_shanghai(self) -> None:
        self.assertRegex(editor.today_shanghai(), r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")

    def test_set_streams_json_only_on_stdin_not_argv_or_log(self) -> None:
        output = StringIO()
        result = Mock(returncode=0)
        with (
            patch.object(editor, "today_shanghai", return_value="2026-09-17"),
            self.answers("", "ordinary days", "My favorite day", "y"),
            patch.object(editor.subprocess, "run", return_value=result) as run,
            redirect_stdout(output),
        ):
            self.assertEqual(editor.main(), 0)
        args = run.call_args.args[0]
        self.assertEqual(args, ["gh", "secret", "set", "DAILY_MESSAGE_CONFIG", "-R",
                                "carloshuangspec/wechat-ldr-daily-push", "--app", "actions"])
        self.assertNotIn("ordinary days", str(args))
        self.assertNotIn("My favorite day", str(args))
        self.assertEqual(
            json.loads(run.call_args.kwargs["input"]),
            {"date": "2026-09-17", "theme": "ordinary days", "exact": "My favorite day"},
        )
        self.assertTrue(run.call_args.kwargs["text"])
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertIn("My favorite day", output.getvalue())  # Local confirmation only.

    def test_cancel_does_not_touch_remote_secret(self) -> None:
        with (
            self.answers("2026-09-17", "ordinary", "", "n"),
            patch.object(editor.subprocess, "run") as run,
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(editor.main(), 0)
        run.assert_not_called()

    def test_blank_or_invalid_exact_fails_before_gh(self) -> None:
        for answer_set in (("2026-09-17", "", ""), ("2026-09-17", "", "A" * 65)):
            with (
                self.subTest(answer_set=answer_set),
                self.answers(*answer_set),
                patch.object(editor.subprocess, "run") as run,
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(editor.main(), 1)
                run.assert_not_called()

    def test_failed_gh_result_hides_its_output(self) -> None:
        output = StringIO()
        result = Mock(returncode=1, stdout="RAW_CONTENT", stderr="RAW_KEY")
        with (
            self.answers("2026-09-17", "", "My day", "y"),
            patch.object(editor.subprocess, "run", return_value=result),
            redirect_stdout(output),
        ):
            self.assertEqual(editor.main(), 1)
        self.assertNotIn("RAW_KEY", output.getvalue())
        self.assertNotIn("RAW_CONTENT", output.getvalue())

    def test_clear_requires_explicit_confirmation_and_targets_only_one_secret(self) -> None:
        with (
            self.answers("clear", "y"),
            patch.object(editor.subprocess, "run", return_value=Mock(returncode=0)) as run,
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(editor.main(), 0)
        self.assertEqual(
            run.call_args.args[0],
            ["gh", "secret", "delete", "DAILY_MESSAGE_CONFIG", "-R",
             "carloshuangspec/wechat-ldr-daily-push", "--app", "actions"],
        )

    def test_keyboard_interrupt_or_missing_gh_is_sanitized(self) -> None:
        with self.answers("2026-09-17", "", "Hello", "y"), patch.object(
            editor.subprocess, "run", side_effect=FileNotFoundError("RAW_PATH")
        ), redirect_stdout(StringIO()) as output:
            self.assertEqual(editor.main(), 1)
        self.assertNotIn("RAW_PATH", output.getvalue())
        with self.answers("2026-09-17", "", "Hello", KeyboardInterrupt()), redirect_stdout(StringIO()):
            self.assertEqual(editor.main(), 1)


if __name__ == "__main__":
    unittest.main()
