"""异地恋每日推送入口：组装数据并发送微信测试号模板消息。"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

from daily_content import (
    ENGLISH_LINE_MAX,
    LOVE_LINE_MAX,
    choose_line,
    contains_forbidden_note_label,
    parse_config,
)
from dates import local_now_str, local_today, love_days, meet_status
from deepseek_line import GENERATED_LINE_MAX, GENERATED_MAX_LINES, generate_love_line
from send_hold import hold_applies, preview_hold, wait_for_send_time
from special_days import get_special_fact
from weather import brief_weather, weather_source
from wechat import build_template_data, send_template


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


class ConfigError(ValueError):
    """安全配置错误；消息不得包含凭据值。"""


def _shanghai_today() -> date:
    return local_today("Asia/Shanghai")


def _label(today: date) -> str:
    return today.strftime("%Y-%m-%d")


def greeting() -> str:
    return "Good morning"


def resolve_send_mode() -> str:
    """解析发送模式；缺失时默认 dry-run，未知值拒绝运行。"""
    mode = _env("SEND_MODE", "dry-run").lower()
    if mode not in {"dry-run", "live"}:
        raise ConfigError("SEND_MODE 只能是 dry-run 或 live")
    return mode


def resolve_openid() -> str:
    """解析当前时段的微信接收人。"""
    slot = _env("PUSH_SLOT", "us")
    if slot == "cn":
        key = "WECHAT_OPENID_CN"
    elif slot == "us":
        key = "WECHAT_OPENID_SELF"
    else:
        raise ConfigError("PUSH_SLOT 只能是 cn 或 us")
    value = _env(key)
    if not value:
        raise ConfigError(f"缺少 {key}")
    return value


def validate_send_context(mode: str) -> None:
    """真发仅允许独立的手动确认或对应收件人已启用的定时上下文。"""
    if mode != "live":
        return
    slot = _env("PUSH_SLOT", "us")
    if slot == "cn":
        return
    if slot != "us":
        raise ConfigError("PUSH_SLOT 只能是 cn 或 us")
    action = _env("GITHUB_EVENT_NAME")
    if action == "workflow_dispatch":
        live_dispatch_mode = _env("LIVE_DISPATCH_MODE")
        live_dispatch_slot = _env("LIVE_DISPATCH_SLOT")
        live_dispatch_date = _env("LIVE_DISPATCH_DATE")
        if (
            live_dispatch_mode != "daily-both"
            or live_dispatch_slot != "both"
            or live_dispatch_date != _shanghai_today().isoformat()
        ):
            raise ConfigError("workflow_dispatch live 需要匹配的 dispatch 上下文")
    elif action == "schedule":
        if _env("ENABLE_SELF_DAILY") != "1":
            raise ConfigError("schedule live 需要 ENABLE_SELF_DAILY=1")
    else:
        raise ConfigError("live 仅允许 workflow_dispatch 或 schedule")


def validate_live_configuration(mode: str, send_hour: int) -> None:
    """真发仅允许受控的定时或手动确认；干跑不检查。"""
    if mode != "live":
        return
    if send_hour not in {6, 7, 8, 9, 10, 11}:
        raise ConfigError("SEND_HOUR 只能是 6 到 11")
    if not _env("WECHAT_TEMPLATE_ID"):
        raise ConfigError("缺少 WECHAT_TEMPLATE_ID")
    _ = resolve_openid()
    if _env("DAILY_CLAIM_CREATED") != "true":
        raise ConfigError("缺少有效的 DAILY_CLAIM_CREATED")
    if _env("DAILY_CLAIM_DATE") != _shanghai_today().isoformat():
        raise ConfigError("DAILY_CLAIM_DATE 与上海日期不匹配")


def build_payload_fields() -> dict:
    """为 dry-run 与 live 共用的一份数据组装；真发时绝不重新生成。"""
    today = _shanghai_today()
    if os.getenv("DAILY_MESSAGE_CONFIG") is not None and os.getenv(
        "DAILY_MESSAGE_CONFIG", ""
    ).strip():
        config = parse_config(os.getenv("DAILY_MESSAGE_CONFIG"))
    else:
        config = None
    known_start = date.fromisoformat(_env("KNOWN_START_DATE", "2019-09-02"))
    love_start = _env("LOVE_START_DATE")
    next_meet = _env("NEXT_MEET_DATE")
    if not love_start:
        raise ConfigError("缺少 LOVE_START_DATE")
    if not next_meet:
        raise ConfigError("缺少 NEXT_MEET_DATE")
    love_start_date = date.fromisoformat(love_start)
    next_meet_date = date.fromisoformat(next_meet)
    love_days_text = str(love_days(love_start_date.isoformat(), today))
    known_days_text = str(love_days(known_start.isoformat(), today))
    city_a = _env("CITY_A", "Ann Arbor")
    city_b = _env("CITY_B", "Shanghai")
    weather_a, weather_b = brief_weather(city_a)
    clock_a = local_now_str(_env("CITY_A_TZ", "America/Detroit"))
    clock_b = local_now_str(_env("CITY_B_TZ", "Asia/Shanghai"))
    if not weather_a or not weather_b or not clock_a or not clock_b:
        raise ConfigError("缺少天气或时钟信息")
    exact, theme, _ = choose_line(config, today)
    if exact is not None:
        short_line = exact
        print("line_source=exact", file=sys.stderr)
        if not (
            isinstance(short_line, str)
            and 1 <= len(short_line) <= ENGLISH_LINE_MAX
            and short_line.isascii()
            and short_line.isprintable()
            and not contains_forbidden_note_label(short_line)
        ):
            raise ConfigError("小信内容非法")
    else:
        special_fact = get_special_fact(
            today, love_start_date, next_meet_date, known_start
        )
        short_line = generate_love_line(
            theme=theme,
            time_a=clock_a,
            time_b=clock_b,
            weather_a=weather_a,
            weather_b=weather_b,
            special_fact=special_fact,
        )
        print("line_source=generated", file=sys.stderr)
        if not (
            isinstance(short_line, str)
            and 1 <= len(short_line) <= GENERATED_LINE_MAX
            and short_line.isascii()
            and len(short_line.split("\n")) <= GENERATED_MAX_LINES
            and all(ch.isprintable() or ch == "\n" for ch in short_line)
            and not contains_forbidden_note_label(short_line)
            and "..." not in short_line
            and "\u2026" not in short_line
        ):
            raise ConfigError("小信内容非法")
    love_line = short_line
    if exact is not None and len(love_line) > LOVE_LINE_MAX:
        raise ConfigError("小信内容超过模板 love_line 长度")
    if exact is None and len(love_line) > GENERATED_LINE_MAX:
        raise ConfigError("小信内容超过模板 love_line 长度")
    countdown = meet_status(next_meet, today)
    visible_line = short_line.strip()
    mirrored = f"{countdown} | {visible_line}"
    if len(mirrored) <= LOVE_LINE_MAX:
        meet_days = mirrored
    elif countdown:
        meet_days = countdown
    else:
        meet_days = ""
    return {
        "date": _label(today),
        "greeting": greeting(),
        "city_a": city_a,
        "time_a": clock_a,
        "weather_a": weather_a,
        "city_b": city_b,
        "time_b": clock_b,
        "weather_b": weather_b,
        "love_days": love_days_text,
        "meet_days": meet_days,
        "love_line": love_line,
        "weather_source": weather_source(),
    }


def build_message_from_fields(fields: dict, dry_run: bool) -> dict:
    """由已组装字段生成模板数据；dry-run 与 live 共用同一份内容。"""
    _ = dry_run
    return build_template_data(fields)


def deliver(payload: dict, dry_run: bool) -> str:
    if dry_run:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    openid = resolve_openid()
    return send_template(openid, payload)


def apply_send_hold(mode: str) -> None:
    if mode != "live":
        return
    if hold_applies():
        wait_for_send_time()
    else:
        preview_hold()


def run() -> int:
    mode = resolve_send_mode()
    validate_send_context(mode)
    send_hour_text = _env("SEND_HOUR", "7")
    if not send_hour_text.isdigit():
        raise ConfigError("SEND_HOUR 必须是数字")
    send_hour = int(send_hour_text)
    validate_live_configuration(mode, send_hour)
    apply_send_hold(mode)
    fields = build_payload_fields()
    payload = build_message_from_fields(fields, mode != "live")
    if mode == "live":
        print("line_source=generated", file=sys.stderr)
        print("live_send_attempt", file=sys.stderr)
        deliver(payload, False)
        return 0
    print("dry_run_payload")
    print(json.dumps(fields, ensure_ascii=False, indent=2, sort_keys=True))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main() -> int:
    try:
        return run()
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - 统一失败出口，不输出凭据
        print(f"运行失败：{type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
