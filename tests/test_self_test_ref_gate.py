"""Isolation branch may live-self; never live-cn or daily-both."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import main  # noqa: E402

ISO_REF = "refs/heads/build/card-layout-c-self-test"

BASE_SELF = {
    "SEND_MODE": "live",
    "PUSH_SLOT": "us",
    "LIVE_RECIPIENT": "self",
    "LIVE_CONFIRMATION": "SEND_SELF_ONCE",
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
    "GITHUB_REF": ISO_REF,
    "GITHUB_ACTOR": "carloshuangspec",
    "GITHUB_TRIGGERING_ACTOR": "carloshuangspec",
    "GITHUB_RUN_ATTEMPT": "1",
}


class IsolationSelfTestRefGateTests(unittest.TestCase):
    def test_live_self_allows_isolation_ref(self) -> None:
        with patch.dict(os.environ, BASE_SELF, clear=True):
            main.validate_send_context("live", "us")

    def test_live_self_still_allows_main(self) -> None:
        with patch.dict(os.environ, {**BASE_SELF, "GITHUB_REF": "refs/heads/main"}, clear=True):
            main.validate_send_context("live", "us")

    def test_live_self_rejects_other_branch(self) -> None:
        with patch.dict(os.environ, {**BASE_SELF, "GITHUB_REF": "refs/heads/build/card-layout-c"}, clear=True):
            with self.assertRaises(main.ConfigError):
                main.validate_send_context("live", "us")

    def test_live_cn_rejects_isolation_ref(self) -> None:
        env = {
            **BASE_SELF,
            "PUSH_SLOT": "cn",
            "LIVE_RECIPIENT": "cn",
            "LIVE_CONFIRMATION": "SEND_CN_ONCE",
            "GITHUB_REF": ISO_REF,
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(main.ConfigError):
                main.validate_send_context("live", "cn")

    def test_live_cn_still_requires_main(self) -> None:
        env = {
            **BASE_SELF,
            "PUSH_SLOT": "cn",
            "LIVE_RECIPIENT": "cn",
            "LIVE_CONFIRMATION": "SEND_CN_ONCE",
            "GITHUB_REF": "refs/heads/main",
        }
        with patch.dict(os.environ, env, clear=True):
            main.validate_send_context("live", "cn")

    def test_daily_both_dispatch_rejects_isolation_ref(self) -> None:
        env = {
            "SEND_MODE": "live",
            "PUSH_SLOT": "cn",
            "LIVE_RECIPIENT": "both",
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
            "GITHUB_REF": ISO_REF,
            "GITHUB_ACTOR": "carloshuangspec",
            "GITHUB_TRIGGERING_ACTOR": "carloshuangspec",
            "GITHUB_RUN_ATTEMPT": "1",
            "ENABLE_CN_DAILY": "1",
            "ENABLE_SELF_DAILY": "1",
            "DAILY_CLAIM_CREATED": "true",
            "DAILY_CLAIM_DATE": "2026-09-18",
            "LIVE_DISPATCH_MODE": "daily-both",
            "LIVE_DISPATCH_SLOT": "both",
            "LIVE_DISPATCH_DATE": "2026-09-18",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today") as today,
        ):
            from datetime import date
            today.return_value = date(2026, 9, 18)
            with self.assertRaises(main.ConfigError):
                main.validate_send_context("live", "cn")


if __name__ == "__main__":
    unittest.main()
