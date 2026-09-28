"""daily-both 发送前的 09:00:00 Asia/Shanghai 精确等待（send hold）。

只在 LIVE Both 的 daily-both 手动派发路径中真正 sleep；预览只记录
``send_hold=would_wait``。所有日志均为固定格式，不含消息正文或凭据。
时钟与 sleep 均可注入，便于测试。
"""

from __future__ import annotations

import os
import sys
import time as _time
from datetime import date, datetime, time
from typing import Callable
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
SEND_AT = time(9, 0, 0)
# 超过该等待时长说明派发异常偏早：不长时间占用 runner，立即发送。
MAX_HOLD_SECONDS = 15 * 60
# 单次 sleep 上限：每段后重新读取墙钟，避免长 sleep 受时钟漂移影响。
MAX_SLEEP_CHUNK = 30.0
# 单调时钟兜底：总等待绝不超过 cap + 该余量。
MONOTONIC_GRACE_SECONDS = 5.0


def _default_now() -> datetime:
    return datetime.now(SHANGHAI)


def _log(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def send_target(delivery_date: date) -> datetime:
    return datetime.combine(delivery_date, SEND_AT, tzinfo=SHANGHAI)


def seconds_until_send(now: datetime, delivery_date: date) -> float:
    """距 delivery_date 09:00:00 Shanghai 的秒数（已过则 <= 0）。"""
    return (send_target(delivery_date) - now.astimezone(SHANGHAI)).total_seconds()


def hold_applies(mode: str, environ: "os._Environ[str] | dict[str, str] | None" = None) -> bool:
    """仅 LIVE Both 的 daily-both 手动派发会真正等待。"""
    env = os.environ if environ is None else environ
    return (
        mode == "live"
        and env.get("LIVE_RECIPIENT") == "both"
        and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and env.get("LIVE_DISPATCH_MODE") == "daily-both"
    )


def preview_hold(
    *,
    now_fn: Callable[[], datetime] = _default_now,
    log: Callable[[str], None] = _log,
) -> str:
    """预览：只报告今天（Shanghai）距 09:00 的等待时长，从不 sleep。"""
    now = now_fn().astimezone(SHANGHAI)
    remaining = seconds_until_send(now, now.date())
    if remaining <= 0:
        log("send_hold=none")
        return "none"
    if remaining > MAX_HOLD_SECONDS:
        log("send_hold=would_skip reason=too_early")
        return "would_skip"
    log(f"send_hold=would_wait seconds={int(round(remaining))}")
    return "would_wait"


def wait_for_send_time(
    delivery_date: date | str | None,
    *,
    now_fn: Callable[[], datetime] = _default_now,
    sleep_fn: Callable[[float], None] = _time.sleep,
    monotonic_fn: Callable[[], float] = _time.monotonic,
    cap_seconds: float = MAX_HOLD_SECONDS,
    log: Callable[[str], None] = _log,
) -> str:
    """若早于 delivery_date 09:00:00 Shanghai 且差值 <= cap，则等待至 09:00:00。

    返回 "none" / "waited" / "skipped"。任何异常情况都选择立即发送，
    绝不无限等待。
    """
    try:
        day = delivery_date if isinstance(delivery_date, date) else date.fromisoformat(str(delivery_date))
    except (TypeError, ValueError):
        log("send_hold=skipped reason=invalid_date")
        return "skipped"

    now = now_fn().astimezone(SHANGHAI)
    remaining = seconds_until_send(now, day)
    if remaining <= 0:
        log("send_hold=none")
        return "none"
    if now.date() != day:
        log("send_hold=skipped reason=date_mismatch")
        return "skipped"
    if remaining > cap_seconds:
        log("send_hold=skipped reason=too_early")
        return "skipped"

    start = monotonic_fn()
    hard_deadline = start + cap_seconds + MONOTONIC_GRACE_SECONDS
    while True:
        remaining = seconds_until_send(now_fn(), day)
        if remaining <= 0:
            break
        budget = hard_deadline - monotonic_fn()
        if budget <= 0:
            break
        sleep_fn(min(remaining, MAX_SLEEP_CHUNK, budget))
    waited = max(0.0, monotonic_fn() - start)
    log(f"send_hold=waited seconds={int(round(waited))}")
    return "waited"
