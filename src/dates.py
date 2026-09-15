"""日期相关：相爱天数与见面倒计时。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def love_days(start: str, today: date | None = None) -> int:
    """自 LOVE_START_DATE 起的天数（含当天记为第 1 天则 +1；这里按已过整天数 +1）。"""
    start_d = date.fromisoformat(start)
    d = today or date.today()
    delta = (d - start_d).days
    return max(delta + 1, 0)


def meet_days(next_meet: str, today: date | None = None) -> int:
    """距 NEXT_MEET_DATE 的倒计时天数；已过则为 0。"""
    meet_d = date.fromisoformat(next_meet)
    d = today or date.today()
    delta = (meet_d - d).days
    return max(delta, 0)


def local_now_str(tz_name: str, fmt: str = "%H:%M") -> str:
    """指定时区当前本地时间短字符串。"""
    now = datetime.now(ZoneInfo(tz_name))
    return now.strftime(fmt)


def local_today(tz_name: str) -> date:
    """指定时区的今日日期。"""
    return datetime.now(ZoneInfo(tz_name)).date()
