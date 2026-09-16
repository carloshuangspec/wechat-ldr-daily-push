"""异地恋每日推送入口：组装数据并发送微信测试号模板消息。"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

from daily_content import choose_line, parse_config
from dates import local_now_str, local_today, love_days, meet_status
from deepseek_line import generate_love_line
from weather import brief_weather, weather_source
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
    """真发仅允许独立的手动确认或明确启用的 CN 定时上下文。"""
    if slot not in {"cn", "us"}:
        raise ConfigError("PUSH_SLOT 只能是 cn 或 us")
    if mode != "live":
        return
    recipient = os.getenv("LIVE_RECIPIENT")
    allowed = {
        "self": ("us", "SEND_SELF_ONCE"),
        "cn": ("cn", "SEND_CN_ONCE"),
    }
    if recipient not in allowed:
        raise ConfigError("live 需要明确的 LIVE_RECIPIENT=self 或 cn")
    expected_slot, expected_confirmation = allowed[recipient]
    if slot != expected_slot:
        raise ConfigError("live 收件角色与 PUSH_SLOT 不匹配")
    # 防误操作门禁：定时 CN 与受控手动发送的条件彼此独立。
    if os.getenv("GITHUB_ACTIONS") != "true":
        raise ConfigError("阶段 C 的 live 仅允许由 GitHub Actions 受控触发")
    if os.getenv("GITHUB_EVENT_NAME") == "schedule":
        expected_schedule = {
            "GITHUB_EVENT_SCHEDULE": "7 8 * * *",
            "ENABLE_CN_DAILY": "1",
            "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        if recipient != "cn" or any(
            os.getenv(name) != value for name, value in expected_schedule.items()
        ):
            raise ConfigError("CN 定时真发上下文不符合门禁")
        return

    if os.getenv("LIVE_CONFIRMATION") != expected_confirmation:
        raise ConfigError("live 缺少精确确认短语")

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
    """按已选角色解析专用 OpenID，不使用通用或另一位接收者回退。"""
    recipient = os.getenv("LIVE_RECIPIENT")
    slot = os.getenv("PUSH_SLOT")
    if (recipient, slot) == ("self", "us"):
        name = "WECHAT_OPENID_SELF"
    elif (recipient, slot) == ("cn", "cn"):
        name = "WECHAT_OPENID_CN"
    else:
        raise ConfigError("live 收件角色与 PUSH_SLOT 不匹配")
    oid = _env(name)
    if not oid:
        raise ConfigError(f"缺少 {name}")
    return oid


def validate_live_configuration() -> str:
    """在任何天气、DeepSeek 或微信请求之前验证真发配置。"""
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
    if not city_a.isascii() or not city_b.isascii():
        raise ConfigError("CITY_A/CITY_B must use English names")
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
    known_start = date.fromisoformat(
        _env("KNOWN_START_DATE", "2019-09-02")
    ).isoformat()
    # 各槽位按对应城市时区计算「今天」。
    today = local_today(tz_b if slot == "cn" else tz_a)
    known_days = love_days(known_start, today=today)
    config = parse_config(os.getenv("DAILY_MESSAGE_CONFIG", "")) if slot == "cn" else None
    exact, theme, _, override_status = choose_line(config, today)
    if slot == "cn":
        print(f"shanghai_day={today.isoformat()} override_status={override_status}", file=sys.stderr)

    weather_a = brief_weather(city_a)
    weather_b = brief_weather(city_b)
    known_suffix = f"\nKnown: ≈{known_days} days"
    if exact is not None:
        short_line = exact
        print("line_source=manual", file=sys.stderr)
    else:
        short_line = generate_love_line(theme=theme)
    if (
        not isinstance(short_line, str)
        or not 1 <= len(short_line) <= 20
        or not short_line.isascii()
        or not short_line.isprintable()
    ):
        raise ConfigError("Invalid English love line")
    # Show the emotional line first even in clients that preview only the first line.
    love_line = short_line + known_suffix
    if len(love_line) > 64:
        raise ConfigError("Love line exceeds template limit")

    ld = love_days(love_start, today=today)
    fields = {
        "greeting": "Good morning, love!",
        "city_a": city_a,
        "time_a": local_now_str(tz_a),
        "weather_a": weather_a,
        "city_b": city_b,
        "time_b": local_now_str(tz_b),
        "weather_b": weather_b,
        "love_days": f"{ld} day" if ld == 1 else f"{ld} days",
        "meet_days": meet_status(next_meet, today=today),
        "love_line": love_line,
        "weather_source": weather_source(),
    }
    for key, value in fields.items():
        if key == "love_line":
            valid = value.endswith(known_suffix) and value[:-len(known_suffix)].isascii()
        elif key in {"weather_a", "weather_b"}:
            valid = value.replace("°", "").isascii()
        else:
            valid = value.isascii()
        if not valid:
            raise ConfigError("Message contains non-English characters")
    return fields


def main() -> int:
    try:
        mode = resolve_send_mode()
        raw_slot = os.getenv("PUSH_SLOT") or ""
        slot = raw_slot.strip().lower()
        validate_send_context(mode, raw_slot if mode == "live" else slot)
        openid = validate_live_configuration() if mode == "live" else ""
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    try:
        fields = build_payload_fields()
        template_data = build_template_data(fields)
        if template_data["love_line"]["value"] != fields["love_line"]:
            raise ConfigError("Love line was not rendered intact")
    except SystemExit:
        raise
    except Exception:
        print("组装数据失败（详情已隐藏）", file=sys.stderr)
        return 1

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
                "deepseek_key_set": bool(_env("DEEPSEEK_API_KEY")),
            },
        }
        print(json.dumps(payload_preview, ensure_ascii=False, indent=2))
        print("SEND_MODE=dry-run：已跳过发送。", file=sys.stderr)
        return 0

    try:
        result = send_template(openid=openid, data=template_data)
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
