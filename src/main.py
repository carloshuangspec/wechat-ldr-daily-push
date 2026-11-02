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


def resolve_send_mode() -> str:
    """解析发送模式；缺失时默认 dry-run，未知值拒绝运行。"""
    mode = _env("SEND_MODE", "dry-run").lower()
    if mode not in {"dry-run", "live"}:
        raise ConfigError("SEND_MODE 只能是 dry-run 或 live")
    return mode


def validate_send_context(mode: str, slot: str) -> None:
    """真发仅允许独立的手动确认或对应收件人已启用的定时上下文。"""
    if slot not in {"cn", "us"}:
        raise ConfigError("PUSH_SLOT 只能是 cn 或 us")
    if mode != "live":
        return
    recipient = os.getenv("LIVE_RECIPIENT")
    allowed = {
        "self": ("us", "SEND_SELF_ONCE"),
        "cn": ("cn", "SEND_CN_ONCE"),
        "both": ("cn", None),
    }
    if recipient not in allowed:
        raise ConfigError("live 需要明确的 LIVE_RECIPIENT=self、cn 或 both")
    expected_slot, expected_confirmation = allowed[recipient]
    if slot != expected_slot:
        raise ConfigError("live 收件角色与 PUSH_SLOT 不匹配")
    # 防误操作门禁：定时发送与受控手动发送的条件彼此独立。
    if os.getenv("GITHUB_ACTIONS") != "true":
        raise ConfigError("阶段 C 的 live 仅允许由 GitHub Actions 受控触发")
    if recipient == "both":
        claimed_day = os.getenv("DAILY_CLAIM_DATE")
        if (
            os.getenv("DAILY_CLAIM_CREATED") != "true"
            or claimed_day != local_today("Asia/Shanghai").isoformat()
            or os.getenv("ENABLE_CN_DAILY") != "1"
            or os.getenv("ENABLE_SELF_DAILY") != "1"
        ):
            raise ConfigError("live-both 需要有效的当日 claim")
        if (
            os.getenv("LIVE_DISPATCH_MODE") != "daily-both"
            or os.getenv("LIVE_DISPATCH_SLOT") != "both"
            or os.getenv("LIVE_DISPATCH_DATE") != claimed_day
        ):
            raise ConfigError("live-both 需要匹配的 dispatch 上下文")
        return
    confirmation = os.getenv("LIVE_CONFIRMATION")
    if confirmation != expected_confirmation:
        raise ConfigError("live 需要正确的 LIVE_CONFIRMATION")


def _load_weather(
    city_a: str, city_b: str, tz_a: str, tz_b: str
) -> tuple[str, str, str, str]:
    weather_a, weather_b = brief_weather(city_a, city_b)
    clock_a = local_now_str(tz_a)
    clock_b = local_now_str(tz_b)
    return weather_a, weather_b, clock_a, clock_b


def build_payload_fields(
    slot: str,
    city_a: str,
    city_b: str,
    tz_a: str,
    tz_b: str,
) -> dict:
    """为 dry-run 与 live 共用的一份数据组装；真发时绝不重新生成。"""
    if slot == "cn":
        config_text = os.environ.get("DAILY_MESSAGE_CONFIG")
        config = parse_config(config_text)
    elif slot == "us":
        config = None
    else:
        raise ConfigError("PUSH_SLOT 只能是 cn 或 us")
    known_start = _env("KNOWN_START_DATE", "2019-09-02")
    love_start = _env("LOVE_START_DATE")
    if not love_start:
        raise ConfigError("缺少 LOVE_START_DATE")
    next_meet = _env("NEXT_MEET_DATE")
    if not next_meet:
        raise ConfigError("缺少 NEXT_MEET_DATE")
    weather_a, weather_b, clock_a, clock_b = _load_weather(city_a, city_b, tz_a, tz_b)
    if slot == "cn":
        today = local_today("Asia/Shanghai")
        date_label = today.isoformat()
    else:
        today = local_today(tz_a)
        date_label = local_today(tz_a).isoformat()
    exact, theme, _, override_status = choose_line(config, today)
    if exact is not None:
        short_line = exact
        if not (
            1 <= len(short_line) <= ENGLISH_LINE_MAX
            and short_line.isascii()
            and short_line.isprintable()
            and not contains_forbidden_note_label(short_line)
        ):
            raise ConfigError("小信内容非法")
    else:
        # 特殊日事实只在生成路径计算：在 theme/exact 选择之后、
        # 调用生成器之前传入；手动 exact 路径保持原样不动。
        try:
            next_meet_date = date.fromisoformat(next_meet)
        except ValueError:
            next_meet_date = None
        special_fact = get_special_fact(
            today,
            date.fromisoformat(love_start),
            next_meet_date,
            date.fromisoformat(known_start),
        )
        short_line = generate_love_line(
            theme,
            time_a=clock_a,
            time_b=clock_b,
            weather_a=weather_a,
            weather_b=weather_b,
            special_fact=special_fact,
        )
        if not (
            1 <= len(short_line) <= GENERATED_LINE_MAX
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
    mirrored = f"{countdown} | {visible_line}" if countdown else visible_line
    if len(mirrored) <= LOVE_LINE_MAX:
        meet_days = mirrored
    elif countdown:
        # 全文放不进现有 meet_days 可用空间时只放倒计时本身，
        # 绝不截断诗句；全文仍保留在 love_line 字段。
        meet_days = countdown
    else:
        # 无倒计时可回退时省略 meet_days，同样不截断诗句。
        meet_days = ""
    fields = {
        "date_label": date_label,
        "known_days": love_days(known_start, today),
        "love_days": love_days(love_start, today),
        "love_line": love_line,
        "meet_days": meet_days,
        "override_status": override_status,
        "weather_a": weather_a,
        "weather_b": weather_b,
        "weather_source": weather_source(),
    }
    return fields


def _preview_payload(fields: dict) -> str:
    return json.dumps(fields, ensure_ascii=False, indent=2, sort_keys=True)


def build_message_from_fields(fields: dict, dry_run: bool) -> str:
    """由已组装字段生成模板数据；dry-run 与 live 共用同一份内容。"""
    _ = dry_run
    payload = build_template_data(
        date_label=fields["date_label"],
        known_days=fields["known_days"],
        love_days=fields["love_days"],
        love_line=fields["love_line"],
        meet_days=fields["meet_days"],
        weather_a=fields["weather_a"],
        weather_b=fields["weather_b"],
        weather_source=fields["weather_source"],
    )
    if fields.get("override_status"):
        payload["override_status"] = fields["override_status"]
    return payload


def deliver(payload: dict, dry_run: bool) -> str:
    if dry_run:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return send_template(payload)


def run() -> str:
    slot = _env("PUSH_SLOT", "cn")
    mode = resolve_send_mode()
    validate_send_context(mode, slot)
    dry_run = mode != "live"
    city_a = _env("CITY_A", "Ann Arbor")
    city_b = _env("CITY_B", "Shanghai")
    tz_a = _env("CITY_A_TZ", "America/Detroit")
    tz_b = _env("CITY_B_TZ", "Asia/Shanghai")
    if not dry_run:
        if hold_applies():
            wait_for_send_time()
        else:
            preview_hold()
    fields = build_payload_fields(slot, city_a, city_b, tz_a, tz_b)
    payload = build_message_from_fields(fields, dry_run)
    if dry_run:
        print(_preview_payload(fields))
    return deliver(payload, dry_run)


def main() -> None:
    try:
        result = run()
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except Exception as exc:  # noqa: BLE001 - 统一失败出口，不输出凭据
        print(f"运行失败：{type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
    if result:
        print(result)


if __name__ == "__main__":
    main()
