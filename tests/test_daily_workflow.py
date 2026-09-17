from __future__ import annotations

import unittest
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily-push.yml"
)


class DailyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        cls.jobs = {
            name: text.split(f"  {name}:\n", 1)[1].split(f"  {next_name}:\n", 1)[0]
            for name, next_name in (
                ("preview-cn", "preview-us"),
                ("preview-us", "live-self"),
                ("live-self", "live-cn"),
                ("live-cn", "scheduled-cn"),
                ("scheduled-cn", "scheduled-self"),
            )
        }
        cls.jobs["scheduled-self"] = text.split("  scheduled-self:\n", 1)[1]

    def test_daily_config_only_loads_in_cn_message_steps(self) -> None:
        for name, job in self.jobs.items():
            with self.subTest(job=name):
                self.assertEqual(
                    job.count("DAILY_MESSAGE_CONFIG: ${{ secrets.DAILY_MESSAGE_CONFIG }}"),
                    1 if name in {"preview-cn", "live-cn", "scheduled-cn"} else 0,
                )

    def test_all_message_steps_use_only_deepseek_key(self) -> None:
        for name, job in self.jobs.items():
            with self.subTest(job=name):
                self.assertEqual(
                    job.count("DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}"), 1
                )
                self.assertNotIn("GEMINI_API_KEY:", job)

    def test_cn_scheduled_preview_is_skipped_when_daily_live_enabled(self) -> None:
        self.assertIn("vars.ENABLE_CN_DAILY != '1'", self.jobs["preview-cn"])
        self.assertIn("vars.ENABLE_CN_DAILY == '1'", self.jobs["scheduled-cn"])
        self.assertIn("vars.ENABLE_SELF_DAILY != '1'", self.jobs["preview-us"])
        self.assertIn("vars.ENABLE_SELF_DAILY == '1'", self.jobs["scheduled-self"])

    def test_live_owner_first_run_and_recipient_separation_stay_intact(self) -> None:
        for name, confirmation, slot in (
            ("live-self", "SEND_SELF_ONCE", "us"),
            ("live-cn", "SEND_CN_ONCE", "cn"),
        ):
            with self.subTest(job=name):
                job = self.jobs[name]
                self.assertIn(f"inputs.confirmation == '{confirmation}'", job)
                self.assertIn(f"inputs.slot == '{slot}'", job)
                self.assertIn("github.ref == 'refs/heads/main'", job)
                self.assertIn("github.run_attempt == '1'", job)
        for name in ("preview-cn", "preview-us"):
            self.assertNotIn("WECHAT_APP_SECRET:", self.jobs[name])
        self.assertNotIn("WECHAT_OPENID_CN:", self.jobs["live-self"])
        self.assertNotIn("WECHAT_OPENID_SELF:", self.jobs["live-cn"])
        self.assertNotIn("WECHAT_OPENID_CN:", self.jobs["scheduled-self"])
        self.assertNotIn("WECHAT_OPENID_SELF:", self.jobs["scheduled-cn"])


if __name__ == "__main__":
    unittest.main()
