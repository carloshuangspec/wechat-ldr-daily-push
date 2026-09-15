"""异地恋每日推送入口：组装数据并发送微信测试号模板消息。"""

from __future__ import annotations

import json
import os
import sys

from dates import local_now_str, local_today, love_days, meet_days
from gemini_line import generate_love_line
from weather import brief_weather
from wechat import build_template_data, send_template


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def resolve_openid() -> str:
    """按 PUSH_SLOT=cn|us 或 WECHAT_OPENID 解析接收方。"""
    slot = _env("PUSH_SLOT").lower()
    if slot == "cn":
        oid = _env("WECHAT_OPENID_CN") or _env("WECHAT_OPENID")
    elif slot == "us":
        oid = _env("WECHAT_OPENID_US") or _env("WECHAT_OPENID")
    else:
        oid = _env("WECHAT_OPENID")
    if not oid:
        raise SystemExit(
            "缺少接收方 OPENID：请设置 WECHAT_OPENID，"
            "或 PUSH_SLOT=cn|us 配合 WECHAT_OPENID_CN / WECHAT_OPENID_US"
        )
    return oid


def build_payload_fields() -> dict[str, str]:
    city_a = _env("CITY_A", "Ann Arbor")
    city_b = _env("CITY_B", "Shanghai")
    tz_a = _env("CITY_A_TZ", "America/Detroit")
    tz_b = _env("CITY_B_TZ", "Asia/Shanghai")

    love_start = _env("LOVE_START_DATE")
    next_meet = _env("NEXT_MEET_DATE")
    if not love_start:
        raise SystemExit("缺少 LOVE_START_DATE (YYYY-MM-DD)")
    if not next_meet:
        raise SystemExit("缺少 NEXT_MEET_DATE (YYYY-MM-DD)")

    # 用城市 A 时区算「今天」，避免跨日边界歧义；也可改用 UTC
    today = local_today(tz_a)

    weather_a = brief_weather(city_a)
    weather_b = brief_weather(city_b)
    love_line = generate_love_line()

    ld = love_days(love_start, today=today)
    md = meet_days(next_meet, today=today)

    return {
        "greeting": "早安，想你了",
        "city_a": city_a,
        "time_a": local_now_str(tz_a),
        "weather_a": weather_a,
        "city_b": city_b,
        "time_b": local_now_str(tz_b),
        "weather_b": weather_b,
        "love_days": f"第{ld}天",
        "meet_days": f"还有{md}天" if md > 0 else "已到期",
        "love_line": love_line,
    }


def main() -> int:
    dry = _env("DRY_RUN") in ("1", "true", "True", "yes", "YES")

    try:
        fields = build_payload_fields()
    except SystemExit:
        raise
    except Exception as e:
        print(f"组装数据失败: {e}", file=sys.stderr)
        return 1

    template_data = build_template_data(fields)
    payload_preview = {
        "touser": "(dry-run)" if dry else resolve_openid(),
        "template_id": _env("WECHAT_TEMPLATE_ID") or "(missing)",
        "data": template_data,
        "meta": {
            "push_slot": _env("PUSH_SLOT") or "(none)",
            "dry_run": dry,
            "qweather_key_set": bool(_env("QWEATHER_KEY")),
            "gemini_key_set": bool(_env("GEMINI_API_KEY")),
        },
    }

    if dry:
        print(json.dumps(payload_preview, ensure_ascii=False, indent=2))
        print("DRY_RUN=1：已跳过发送。", file=sys.stderr)
        return 0

    openid = resolve_openid()
    if not _env("WECHAT_APP_ID") or not _env("WECHAT_APP_SECRET"):
        print("缺少 WECHAT_APP_ID / WECHAT_APP_SECRET", file=sys.stderr)
        return 1
    if not _env("WECHAT_TEMPLATE_ID"):
        print("缺少 WECHAT_TEMPLATE_ID", file=sys.stderr)
        return 1

    try:
        result = send_template(openid=openid, data=fields)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"发送失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
