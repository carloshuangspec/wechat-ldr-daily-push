"""异地恋每日推送入口：组装数据并发送微信测试号模板消息。"""

from __future__ import annotations

import json
import os
import sys

from dates import local_now_str, local_today, love_days, meet_status
from gemini_line import generate_love_line
from weather import brief_weather
from wechat import build_template_data, send_template


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


class ConfigError(ValueError):
    """安全配置错误；消息不得包含凭据值。"""


def resolve_send_mode() -> str:
    """解析发送模式；缺失时默认 dry-run，未知值拒绝运行。"""
    mode = _env("SEND_MODE", "dry-run").lower()
    if mode not in {"dry-run", "live"}:
        raise ConfigError("SEND_MODE 只能是 dry-run 或 live")
    return mode


def validate_send_context(mode: str, slot: str) -> None:
    """阶段 C 只允许一次受控 workflow_dispatch 进入 CN 真发。"""
    if slot not in {"cn", "us"}:
        raise ConfigError("PUSH_SLOT 只能是 cn 或 us")
    if mode != "live":
        return
    if slot != "cn":
        raise ConfigError("阶段 C 仅允许 PUSH_SLOT=cn 使用 live 模式")
    if _env("LIVE_CONFIRMATION") != "SEND_CN_ONCE":
        raise ConfigError("live 缺少精确确认短语")

    # 防误操作门禁：阶段 C 只接受与受控 workflow_dispatch 匹配的上下文。
    if _env("GITHUB_ACTIONS").lower() != "true":
        raise ConfigError("阶段 C 的 live 仅允许由 GitHub Actions 受控触发")
    expected = {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_ACTOR": "carloshuangspec",
        "GITHUB_TRIGGERING_ACTOR": "carloshuangspec",
        "GITHUB_RUN_ATTEMPT": "1",
    }
    if any(_env(name) != value for name, value in expected.items()):
        raise ConfigError("GitHub Actions 真发上下文不符合阶段 C 门禁")


def resolve_openid() -> str:
    """阶段 C 仅解析专用的 CN 接收方，不使用通用或 US 回退。"""
    slot = _env("PUSH_SLOT").lower()
    if slot != "cn":
        raise ConfigError("阶段 C 只能解析 CN 接收方")
    oid = _env("WECHAT_OPENID_CN")
    if not oid:
        raise ConfigError("缺少 WECHAT_OPENID_CN")
    return oid


def validate_live_configuration() -> str:
    """在任何天气、Gemini 或微信请求之前验证 CN 真发配置。"""
    missing = [
        name
        for name in ("WECHAT_APP_ID", "WECHAT_APP_SECRET", "WECHAT_TEMPLATE_ID")
        if not _env(name)
    ]
    if missing:
        raise ConfigError("缺少微信真发必填配置")
    return resolve_openid()


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

    slot = _env("PUSH_SLOT").lower()
    if slot not in {"cn", "us"}:
        raise ConfigError("PUSH_SLOT 只能是 cn 或 us")
    # 各槽位按对应城市时区计算「今天」。
    today = local_today(tz_b if slot == "cn" else tz_a)

    weather_a = brief_weather(city_a)
    weather_b = brief_weather(city_b)
    love_line = generate_love_line()

    ld = love_days(love_start, today=today)
    return {
        "greeting": "早安，想你了",
        "city_a": city_a,
        "time_a": local_now_str(tz_a),
        "weather_a": weather_a,
        "city_b": city_b,
        "time_b": local_now_str(tz_b),
        "weather_b": weather_b,
        "love_days": f"第{ld}天",
        "meet_days": meet_status(next_meet, today=today),
        "love_line": love_line,
        "weather_source": "QWeather https://www.qweather.com",
    }


def main() -> int:
    try:
        mode = resolve_send_mode()
        slot = _env("PUSH_SLOT").lower()
        validate_send_context(mode, slot)
        openid = validate_live_configuration() if mode == "live" else ""
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    try:
        fields = build_payload_fields()
    except SystemExit:
        raise
    except Exception:
        print("组装数据失败（详情已隐藏）", file=sys.stderr)
        return 1

    template_data = build_template_data(fields)
    if mode == "dry-run":
        payload_preview = {
            "touser": "(dry-run; WeChat credentials not loaded)",
            "template_id": "(dry-run; WeChat credentials not loaded)",
            "data": template_data,
            "meta": {
                "push_slot": slot,
                "send_mode": mode,
                "qweather_key_set": bool(_env("QWEATHER_KEY")),
                "qweather_host_set": bool(_env("QWEATHER_API_HOST")),
                "gemini_key_set": bool(_env("GEMINI_API_KEY")),
            },
        }
        print(json.dumps(payload_preview, ensure_ascii=False, indent=2))
        print("SEND_MODE=dry-run：已跳过发送。", file=sys.stderr)
        return 0

    try:
        result = send_template(openid=openid, data=fields)
        safe_result = {
            "ok": True,
            "errcode": result["errcode"],
            "msgid": result["msgid"],
        }
        print(json.dumps(safe_result, ensure_ascii=False))
        return 0
    except Exception:
        print("发送失败（详情已脱敏）", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
