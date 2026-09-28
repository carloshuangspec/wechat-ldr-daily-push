"""09:00:00 Asia/Shanghai send hold for the LIVE Both daily-both path."""

from __future__ import annotations

import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import main  # noqa: E402
import send_hold  # noqa: E402
from send_hold import SHANGHAI  # noqa: E402

DAY = date(2026, 9, 17)


class FakeClock:
    """Wall clock + monotonic clock that advance together on sleep."""

    def __init__(self, start: datetime) -> None:
        self.wall = start
        self.mono = 1000.0
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    def sleep(self, seconds: float) -> None:
        assert seconds > 0
        self.sleeps.append(seconds)
        self.wall += timedelta(seconds=seconds)
        self.mono += seconds


def at(h: int, m: int, s: int = 0, us: int = 0, day: date = DAY) -> datetime:
    return datetime(day.year, day.month, day.day, h, m, s, us, tzinfo=SHANGHAI)


def run_hold(clock: FakeClock, day=DAY):
    logs: list[str] = []
    status = send_hold.wait_for_send_time(
        day,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
        monotonic_fn=clock.monotonic,
        log=logs.append,
    )
    return status, logs


PAIRED_DISPATCH_ENV = {
    "SEND_MODE": "live",
    "PUSH_SLOT": "cn",
    "LIVE_RECIPIENT": "both",
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_ACTOR": "carloshuangspec",
    "GITHUB_TRIGGERING_ACTOR": "carloshuangspec",
    "GITHUB_RUN_ATTEMPT": "1",
    "ENABLE_CN_DAILY": "1",
    "ENABLE_SELF_DAILY": "1",
    "DAILY_CLAIM_CREATED": "true",
    "DAILY_CLAIM_DATE": "2026-09-17",
    "LIVE_DISPATCH_MODE": "daily-both",
    "LIVE_DISPATCH_SLOT": "both",
    "LIVE_DISPATCH_DATE": "2026-09-17",
    "WECHAT_APP_ID": "TEST_APP",
    "WECHAT_APP_SECRET": "TEST_SECRET_NOT_FOR_LOGS",
    "WECHAT_TEMPLATE_ID": "TEST_TEMPLATE_NOT_FOR_LOGS",
    "WECHAT_OPENID_CN": "TEST_CN_OPENID_NOT_FOR_LOGS",
    "WECHAT_OPENID_SELF": "TEST_SELF_OPENID_NOT_FOR_LOGS",
    "LOVE_START_DATE": "2026-07-08",
    "NEXT_MEET_DATE": "2026-12-20",
}
FIELDS = {"meet_days": "today | BODY_MARKER_NOT_FOR_LOGS", "love_line": "BODY_MARKER_NOT_FOR_LOGS", "greeting": "Known: ≈1 days"}


class WaitForSendTimeTests(unittest.TestCase):
    def test_before_nine_waits_exact_remaining_seconds(self) -> None:
        clock = FakeClock(at(8, 56, 30))
        status, logs = run_hold(clock)
        self.assertEqual(status, "waited")
        self.assertEqual(clock.wall, at(9, 0, 0))
        self.assertAlmostEqual(sum(clock.sleeps), 210.0)
        self.assertTrue(all(s <= send_hold.MAX_SLEEP_CHUNK for s in clock.sleeps))
        self.assertEqual(logs, ["send_hold=waited seconds=210"])

    def test_sub_second_remaining_is_honoured(self) -> None:
        clock = FakeClock(at(8, 59, 59, 250000))
        status, logs = run_hold(clock)
        self.assertEqual(status, "waited")
        self.assertEqual(clock.wall, at(9, 0, 0))
        self.assertEqual(logs, ["send_hold=waited seconds=1"])

    def test_wall_clock_is_rechecked_between_chunks(self) -> None:
        clock = FakeClock(at(8, 58, 0))
        original = clock.sleep

        def sleep_with_ntp_jump(seconds: float) -> None:
            original(seconds)
            if len(clock.sleeps) == 1:
                clock.wall += timedelta(seconds=45)  # wall clock stepped forward

        clock.sleep = sleep_with_ntp_jump  # type: ignore[method-assign]
        status, _ = run_hold(clock)
        self.assertEqual(status, "waited")
        self.assertGreaterEqual(clock.wall, at(9, 0, 0))
        self.assertAlmostEqual(sum(clock.sleeps), 75.0)

    def test_monotonic_cap_bounds_wait_even_if_wall_clock_stalls(self) -> None:
        clock = FakeClock(at(8, 50, 0))

        def stalled_sleep(seconds: float) -> None:
            clock.sleeps.append(seconds)
            clock.mono += seconds  # wall clock never advances

        clock.sleep = stalled_sleep  # type: ignore[method-assign]
        status, logs = run_hold(clock)
        self.assertEqual(status, "waited")
        self.assertLessEqual(
            sum(clock.sleeps),
            send_hold.MAX_HOLD_SECONDS + send_hold.MONOTONIC_GRACE_SECONDS + 1e-6,
        )
        self.assertTrue(logs[0].startswith("send_hold=waited seconds="))

    def test_exactly_nine_does_not_wait(self) -> None:
        clock = FakeClock(at(9, 0, 0))
        self.assertEqual(run_hold(clock), ("none", ["send_hold=none"]))
        self.assertEqual(clock.sleeps, [])

    def test_after_nine_does_not_wait(self) -> None:
        for start in (at(9, 0, 0, 1), at(9, 1, 30), at(23, 59, 59)):
            with self.subTest(start=start):
                clock = FakeClock(start)
                self.assertEqual(run_hold(clock), ("none", ["send_hold=none"]))
                self.assertEqual(clock.sleeps, [])

    def test_more_than_fifteen_minutes_early_skips_and_sends_now(self) -> None:
        for start in (at(8, 44, 59), at(7, 0, 0), at(0, 0, 1)):
            with self.subTest(start=start):
                clock = FakeClock(start)
                self.assertEqual(
                    run_hold(clock), ("skipped", ["send_hold=skipped reason=too_early"])
                )
                self.assertEqual(clock.sleeps, [])

    def test_exactly_fifteen_minutes_early_waits(self) -> None:
        clock = FakeClock(at(8, 45, 0))
        status, logs = run_hold(clock)
        self.assertEqual(status, "waited")
        self.assertEqual(logs, ["send_hold=waited seconds=900"])

    def test_other_timezone_input_is_converted_to_shanghai(self) -> None:
        detroit = at(8, 58, 0).astimezone(send_hold.ZoneInfo("America/Detroit"))
        clock = FakeClock(detroit)
        status, logs = run_hold(clock)
        self.assertEqual(status, "waited")
        self.assertEqual(logs, ["send_hold=waited seconds=120"])

    def test_previous_day_or_invalid_date_never_waits(self) -> None:
        clock = FakeClock(at(8, 59, 0, day=date(2026, 9, 16)))
        self.assertEqual(run_hold(clock)[0], "skipped")
        for bad in (None, "", "not-a-date"):
            clock = FakeClock(at(8, 59, 0))
            self.assertEqual(
                run_hold(clock, day=bad), ("skipped", ["send_hold=skipped reason=invalid_date"])
            )
            self.assertEqual(clock.sleeps, [])

    def test_accepts_iso_string_delivery_date(self) -> None:
        clock = FakeClock(at(8, 59, 0))
        self.assertEqual(run_hold(clock, day="2026-09-17")[0], "waited")


class PreviewHoldTests(unittest.TestCase):
    def test_preview_logs_would_wait_without_sleeping(self) -> None:
        logs: list[str] = []
        with patch.object(send_hold._time, "sleep") as sleep:
            status = send_hold.preview_hold(now_fn=lambda: at(8, 57, 0), log=logs.append)
        sleep.assert_not_called()
        self.assertEqual(status, "would_wait")
        self.assertEqual(logs, ["send_hold=would_wait seconds=180"])

    def test_preview_after_nine_or_too_early(self) -> None:
        logs: list[str] = []
        send_hold.preview_hold(now_fn=lambda: at(9, 5, 0), log=logs.append)
        send_hold.preview_hold(now_fn=lambda: at(6, 0, 0), log=logs.append)
        self.assertEqual(logs, ["send_hold=none", "send_hold=would_skip reason=too_early"])


class HoldGatingTests(unittest.TestCase):
    def test_only_live_both_daily_both_dispatch_applies(self) -> None:
        self.assertTrue(send_hold.hold_applies("live", PAIRED_DISPATCH_ENV))
        variants = [
            ("dry-run", {}),
            ("live", {"LIVE_RECIPIENT": "cn"}),
            ("live", {"LIVE_RECIPIENT": "self"}),
            ("live", {"GITHUB_EVENT_NAME": "schedule", "LIVE_DISPATCH_MODE": ""}),
            ("live", {"LIVE_DISPATCH_MODE": "live-cn"}),
            ("live", {"LIVE_DISPATCH_MODE": "live-self"}),
            ("live", {"LIVE_DISPATCH_MODE": "preview"}),
            ("live", {"LIVE_DISPATCH_MODE": " daily-both "}),
        ]
        for mode, override in variants:
            with self.subTest(mode=mode, override=override):
                env = {**PAIRED_DISPATCH_ENV, **override}
                self.assertFalse(send_hold.hold_applies(mode, env))


class MainIntegrationTests(unittest.TestCase):
    def _run_main(self, env, clock: FakeClock):
        events: list[str] = []
        stdout, stderr = StringIO(), StringIO()

        def fake_wait(day):
            events.append("hold")
            return send_hold.wait_for_send_time(
                day, now_fn=clock.now, sleep_fn=clock.sleep, monotonic_fn=clock.monotonic
            )

        def fake_send(openid, data):
            events.append(f"send@{clock.now().time().isoformat()}")
            return {"errcode": 0, "msgid": "1"}

        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(main, "local_today", return_value=DAY),
            patch.object(main, "build_payload_fields", side_effect=lambda: events.append("build") or dict(FIELDS)),
            patch.object(main, "wait_for_send_time", side_effect=fake_wait),
            patch.object(main, "preview_hold", side_effect=lambda: send_hold.preview_hold(now_fn=clock.now)),
            patch.object(main, "send_template", side_effect=fake_send) as send,
            patch.object(send_hold._time, "sleep", side_effect=AssertionError("real sleep")),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            rc = main.main()
        return rc, events, stdout.getvalue(), stderr.getvalue(), send

    def test_daily_both_builds_then_holds_then_sends_both_back_to_back(self) -> None:
        clock = FakeClock(at(8, 57, 10))
        rc, events, out, err, send = self._run_main(PAIRED_DISPATCH_ENV, clock)
        self.assertEqual(rc, 0)
        self.assertEqual(events, ["build", "hold", "send@09:00:00", "send@09:00:00"])
        self.assertEqual(
            [c.kwargs["openid"] for c in send.call_args_list],
            [PAIRED_DISPATCH_ENV["WECHAT_OPENID_CN"], PAIRED_DISPATCH_ENV["WECHAT_OPENID_SELF"]],
        )
        self.assertIn("send_hold=waited seconds=170", err)
        for secret in ("WECHAT_APP_SECRET", "WECHAT_TEMPLATE_ID", "WECHAT_OPENID_CN", "WECHAT_OPENID_SELF"):
            self.assertNotIn(PAIRED_DISPATCH_ENV[secret], out + err)
        self.assertNotIn("BODY_MARKER_NOT_FOR_LOGS", out + err)

    def test_daily_both_after_nine_sends_immediately(self) -> None:
        clock = FakeClock(at(9, 0, 3))
        rc, events, _, err, _ = self._run_main(PAIRED_DISPATCH_ENV, clock)
        self.assertEqual(rc, 0)
        self.assertEqual(clock.sleeps, [])
        self.assertEqual(events, ["build", "hold", "send@09:00:03", "send@09:00:03"])
        self.assertIn("send_hold=none", err)

    def test_daily_both_too_early_sends_immediately(self) -> None:
        clock = FakeClock(at(8, 30, 0))
        rc, events, _, err, send = self._run_main(PAIRED_DISPATCH_ENV, clock)
        self.assertEqual(rc, 0)
        self.assertEqual(clock.sleeps, [])
        self.assertEqual(send.call_count, 2)
        self.assertIn("send_hold=skipped reason=too_early", err)

    def test_gate_failure_never_reaches_hold(self) -> None:
        clock = FakeClock(at(8, 57, 0))
        env = {**PAIRED_DISPATCH_ENV, "LIVE_DISPATCH_DATE": "2026-09-16"}
        rc, events, _, err, send = self._run_main(env, clock)
        self.assertEqual(rc, 2)
        self.assertEqual(events, [])
        send.assert_not_called()
        self.assertNotIn("send_hold=", err)

    def test_non_daily_both_modes_never_hold_or_sleep(self) -> None:
        schedule_both = {**PAIRED_DISPATCH_ENV, "GITHUB_EVENT_NAME": "schedule", "GITHUB_EVENT_SCHEDULE": "0 9 * * *"}
        for key in ("LIVE_DISPATCH_MODE", "LIVE_DISPATCH_SLOT", "LIVE_DISPATCH_DATE", "GITHUB_ACTOR", "GITHUB_TRIGGERING_ACTOR"):
            schedule_both.pop(key)
        live_cn = {
            **PAIRED_DISPATCH_ENV, "LIVE_RECIPIENT": "cn", "LIVE_CONFIRMATION": "SEND_CN_ONCE",
            "ENABLE_SELF_DAILY": "", "ENABLE_CN_DAILY": "",
        }
        live_self = {
            **live_cn, "LIVE_RECIPIENT": "self", "PUSH_SLOT": "us", "LIVE_CONFIRMATION": "SEND_SELF_ONCE",
        }
        preview_cn = {"SEND_MODE": "dry-run", "PUSH_SLOT": "cn"}
        for name, env in (("schedule-both", schedule_both), ("live-cn", live_cn), ("live-self", live_self), ("preview-cn", preview_cn)):
            with self.subTest(name=name):
                clock = FakeClock(at(8, 57, 0))
                rc, events, _, err, _ = self._run_main(env, clock)
                self.assertEqual(rc, 0)
                self.assertNotIn("hold", events)
                self.assertEqual(clock.sleeps, [])
                self.assertNotIn("send_hold=", err)

    def test_preview_both_logs_would_wait_without_sleeping(self) -> None:
        clock = FakeClock(at(8, 58, 0))
        env = {"SEND_MODE": "dry-run", "PUSH_SLOT": "cn", "LIVE_RECIPIENT": "both"}
        rc, events, _, err, send = self._run_main(env, clock)
        self.assertEqual(rc, 0)
        self.assertEqual(clock.sleeps, [])
        send.assert_not_called()
        self.assertNotIn("hold", events)
        self.assertIn("send_hold=would_wait seconds=120", err)

    def test_hold_error_sends_immediately(self) -> None:
        with (
            patch.dict(os.environ, PAIRED_DISPATCH_ENV, clear=True),
            patch.object(main, "local_today", return_value=DAY),
            patch.object(main, "build_payload_fields", return_value=dict(FIELDS)),
            patch.object(main, "wait_for_send_time", side_effect=RuntimeError("BODY_MARKER_NOT_FOR_LOGS")),
            patch.object(main, "send_template", return_value={"errcode": 0, "msgid": "1"}) as send,
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()) as err,
        ):
            self.assertEqual(main.main(), 0)
        self.assertEqual(send.call_count, 2)
        self.assertIn("send_hold=skipped reason=error", err.getvalue())
        self.assertNotIn("BODY_MARKER_NOT_FOR_LOGS", err.getvalue())


class WorkflowTimeoutTests(unittest.TestCase):
    def test_daily_both_job_timeout_covers_cap(self) -> None:
        workflow = (ROOT / ".github/workflows/daily-push.yml").read_text(encoding="utf-8")
        both_job = workflow.split("  daily-both:\n", 1)[1]
        self.assertIn("timeout-minutes: 25", both_job)
        self.assertGreaterEqual(25 * 60, send_hold.MAX_HOLD_SECONDS + 5 * 60)


if __name__ == "__main__":
    unittest.main()
