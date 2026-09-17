"""The remote template diagnostic must not send or reveal account values."""

from __future__ import annotations

import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import wechat  # noqa: E402


class TemplateInspectionTests(unittest.TestCase):
    @staticmethod
    def response(data: object, status: int = 200) -> Mock:
        response = Mock()
        response.status_code = status
        response.raise_for_status.return_value = None
        response.json.return_value = data
        return response

    def test_existing_template_reports_missing_line_without_leaking_content(self) -> None:
        response = self.response({
            "template_list": [{
                "template_id": "TEST_TEMPLATE_SECRET",
                "content": "{{greeting.DATA}}\nTogether: {{love_days.DATA}}",
            }],
        })
        inspect = getattr(wechat, "inspect_template_fields", lambda *_: None)
        with patch.object(wechat.requests, "get", return_value=response) as get:
            result = inspect("TEST_TEMPLATE_SECRET", "TEST_TOKEN_SECRET")
        self.assertIsInstance(result, dict)
        self.assertTrue(result["template_found"])
        self.assertIn("love_line", result["missing_fields"])
        self.assertNotIn("greeting", result["missing_fields"])
        self.assertEqual(result["field_lines"], [["greeting"], ["love_days"]])
        self.assertEqual(result["content_chars"], len("{{greeting.DATA}}\nTogether: {{love_days.DATA}}"))
        self.assertNotIn("TEST_TEMPLATE_SECRET", str(result))
        self.assertNotIn("TEST_TOKEN_SECRET", str(result))
        self.assertIs(get.call_args.kwargs["allow_redirects"], False)

    def test_complete_template_has_no_missing_fields(self) -> None:
        content = "\n".join(
            "{{" + key + ".DATA}}" for key in (
                "greeting", "city_a", "time_a", "weather_a", "city_b", "time_b",
                "weather_b", "love_days", "meet_days", "love_line", "weather_source",
            )
        )
        response = self.response({
            "template_list": [{"template_id": "MATCH", "content": content}]
        })
        inspect = getattr(wechat, "inspect_template_fields", lambda *_: None)
        with patch.object(wechat.requests, "get", return_value=response):
            self.assertEqual(
                inspect("MATCH", "token"),
                {
                    "template_found": True,
                    "missing_fields": [],
                    "content_chars": len(content),
                    "field_lines": [[key] for key in (
                        "greeting", "city_a", "time_a", "weather_a", "city_b",
                        "time_b", "weather_b", "love_days", "meet_days",
                        "love_line", "weather_source",
                    )],
                },
            )

    def test_missing_template_is_distinct_from_missing_variable(self) -> None:
        response = self.response({
            "template_list": [{"template_id": "ANOTHER", "content": "{{love_line.DATA}}"}]
        })
        inspect = getattr(wechat, "inspect_template_fields", lambda *_: None)
        with patch.object(wechat.requests, "get", return_value=response):
            self.assertEqual(
                inspect("EXPECTED", "token"),
                {
                    "template_found": False,
                    "missing_fields": [],
                    "content_chars": 0,
                    "field_lines": [],
                },
            )

    def test_outline_never_exposes_fixed_template_text(self) -> None:
        content = "PRIVATE_LABEL {{love_line.DATA}}\n{{greeting.DATA}}"
        response = self.response({
            "template_list": [{"template_id": "MATCH", "content": content}]
        })
        inspect = getattr(wechat, "inspect_template_fields", lambda *_: None)
        with patch.object(wechat.requests, "get", return_value=response):
            result = inspect("MATCH", "token")
        self.assertEqual(result["field_lines"], [["love_line"], ["greeting"]])
        self.assertNotIn("PRIVATE_LABEL", str(result))

    def test_network_failure_does_not_expose_token(self) -> None:
        inspect = getattr(wechat, "inspect_template_fields", lambda *_: None)
        with patch.object(
            wechat.requests, "get", side_effect=requests.RequestException("TEST_TOKEN_SECRET")
        ):
            with self.assertRaises(wechat.WeChatAPIError) as caught:
                inspect("MATCH", "TEST_TOKEN_SECRET")
        self.assertNotIn("TEST_TOKEN_SECRET", str(caught.exception))

    def test_diagnostic_cli_only_prints_boolean_and_missing_names(self) -> None:
        import importlib

        inspect_script = importlib.util.find_spec("inspect_template")
        self.assertIsNotNone(inspect_script)
        module = importlib.import_module("inspect_template")
        stdout, stderr = StringIO(), StringIO()
        with (
            patch.object(module, "inspect_template_fields", return_value={
                "template_found": True, "missing_fields": ["love_line"]
            }),
            patch.dict("os.environ", {"WECHAT_TEMPLATE_ID": "TEST_TEMPLATE_SECRET"}),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(module.main(), 2)
        self.assertEqual(json.loads(stdout.getvalue()), {
            "template_found": True, "missing_fields": ["love_line"]
        })
        self.assertNotIn("TEST_TEMPLATE_SECRET", stdout.getvalue() + stderr.getvalue())

    def test_workflow_is_manual_read_only_and_loads_no_recipient(self) -> None:
        path = ROOT / ".github" / "workflows" / "inspect-template.yml"
        self.assertTrue(path.exists())
        workflow = path.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("github.actor == 'carloshuangspec'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("WECHAT_APP_SECRET: ${{ secrets.WECHAT_APP_SECRET }}", workflow)
        self.assertNotIn("WECHAT_OPENID_", workflow)
        self.assertNotIn("DEEPSEEK_API_KEY:", workflow)
        self.assertNotIn("send_template", workflow)


if __name__ == "__main__":
    unittest.main()
