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
    if mode != "live":
        return
    if slot not in {"cn", "us"}:
        raise ConfigError("PUSH_SLOT 只能是 cn 或 us")
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


def validate_live_configuration() -> list[tuple[str, str]]:
    """校验真发配置，返回按发送顺序排列的 (role, openid)；不返回凭据。"""
    if not _env("WECHAT_APP_ID") or not _env("WECHAT_APP_SECRET"):
        raise ConfigError("缺少微信应用凭据")
    if not _env("WECHAT_TEMPLATE_ID"):
        raise ConfigError("缺少 WECHAT_TEMPLATE_ID")
    recipient = os.getenv("LIVE_RECIPIENT")
    if recipient == "both":
        cn_openid = _env("WECHAT_OPENID_CN")
        self_openid = _env("WECHAT_OPENID_SELF")
        if not cn_openid or not self_openid:
            raise ConfigError("缺少双人真发 OpenID")
        if cn_openid == self_openid:
            raise ConfigError("双人真发 OpenID 不能相同")
        return [("cn", cn_openid), ("self", self_openid)]
    return [(os.environ["LIVE_RECIPIENT"], resolve_openid())]


def build_payload_fields() -> dict[str, str]:
    """为 dry-run 与 live 共用的一份数据组装；真发时绝不重新生成。"""
    city_a = _env("CITY_A", "Ann Arbor")
    city_b = _env("CITY_B", "Shanghai")
    if not city_a.isascii() or not city_b.isascii():
        raise ConfigError("城市名必须为英文")
    tz_a = _env("CITY_A_TZ", "America/Detroit")
    tz_b = _env("CITY_B_TZ", "Asia/Shanghai")
    slot = _env("PUSH_SLOT").lower()
    if slot not in {"cn", "us"}:
        raise ConfigError("PUSH_SLOT 只能是 cn 或 us")
    known_start = date.fromisoformat(_env("KNOWN_START_DATE", "2019-09-02")).isoformat()
    love_start = _env("LOVE_START_DATE")
    next_meet = _env("NEXT_MEET_DATE")
    paired_delivery = os.getenv("LIVE_RECIPIENT") == "both"
    today = local_today("Asia/Shanghai" if paired_delivery else (tz_b if slot == "cn" else tz_a))
    if paired_delivery and _env("SEND_MODE").lower() == "live" and today.isoformat() != _env("DAILY_CLAIM_DATE"):
        raise ConfigError("双人真发日期已变化，已停止发送")
    known_days = love_days(known_start, today=today)
    if slot == "cn" and _env("DAILY_MESSAGE_CONFIG"):
        config = parse_config(_env("DAILY_MESSAGE_CONFIG"))
    else:
        config = None
    exact, theme, _, override_status = choose_line(config, today)
    if slot == "cn":
        print(f"shanghai_day={today.isoformat()} override_status={override_status}", file=sys.stderr)
    weather_a = brief_weather(city_a)
    weather_b = brief_weather(city_b)
    time_a = local_now_str(tz_a)
    time_b = local_now_str(tz_b)
    if exact is not None:
        short_line = exact
        print("line_source=manual", file=sys.stderr)
    else:
        # 特殊日事实只在生成路径计算：在 theme/exact 选择之后、
        # 调用生成器之前传入；手动 exact 路径保持原样不动。
        special_fact = get_special_fact(
            today,
            date.fromisoformat(love_start),
            date.fromisoformat(next_meet),
            date.fromisoformat(known_start),
        )
        short_line = generate_love_line(
            theme=theme,
            time_a=time_a,
            time_b=time_b,
            weather_a=weather_a,
            weather_b=weather_b,
            special_fact=special_fact,
        )
    if exact is not None:
        if (
            not isinstance(short_line, str)
            or not (1 <= len(short_line) <= ENGLISH_LINE_MAX)
            or not short_line.isascii()
            or not short_line.isprintable()
            or contains_forbidden_note_label(short_line)
        ):
            raise ConfigError("Invalid English love line")
    else:
        if (
            not isinstance(short_line, str)
            or not (1 <= len(short_line) <= GENERATED_LINE_MAX)
            or not short_line.isascii()
            or len(short_line.split("\n")) > GENERATED_MAX_LINES
            or any(not ch.isprintable() and ch != "\n" for ch in short_line)
            or contains_forbidden_note_label(short_line)
            or "..." in short_line
            or "\u2026" in short_line
        ):
            raise ConfigError("Invalid English love line")
    # The visible card shows meet_days; it must never show a clipped line,
    # so the love line must fit beside the countdown, not just on its own.
    love_line = short_line
    if exact is not None and len(love_line) > LOVE_LINE_MAX:
        raise ConfigError("Love line exceeds template limit")
    if exact is None and len(love_line) > GENERATED_LINE_MAX:
        raise ConfigError("Love line exceeds template limit")
    countdown = meet_status(next_meet, today=today)
    visible_line = short_line.strip()
    if not visible_line:
        raise ConfigError("Love line has no visible text")
    mirrored = f"{countdown} | {visible_line}"
    if exact is not None:
        available = LOVE_LINE_MAX - len(countdown) - len(" | ")
        if available < 1:
            raise ConfigError("Meeting field has no room for the love line")
        if len(visible_line) > available:
            raise ConfigError("Love line exceeds visible meeting field")
        meet_days = mirrored
    elif len(mirrored) <= LOVE_LINE_MAX:
        meet_days = mirrored
    elif countdown:
        # 全文放不进现有 meet_days 可用空间时只放倒计时本身，
        # 绝不截断诗句；全文仍保留在 love_line 字段。
        meet_days = countdown
    else:
        meet_days = ""
    greeting = f"Known: \u2248{known_days} days"
    if len(greeting) > 20:
        greeting = f"Known \u2248{known_days}d"
    if len(greeting) > 20:
        raise ConfigError("Known greeting exceeds template limit")
    ld = love_days(love_start, today=today)
    fields = {
        "greeting": greeting,
        "city_a": city_a,
        "time_a": time_a,
        "weather_a": weather_a,
        "city_b": city_b,
        "time_b": time_b,
        "weather_b": weather_b,
        "love_days": f"{ld} day" if ld == 1 else f"{ld} days",
        "meet_days": meet_days,
        "love_line": love_line,
        "weather_source": weather_source(),
    }
    for key, value in fields.items():
        if key == "greeting":
            valid = value.replace("\u2248", "").isascii()
        elif key in {"weather_a", "weather_b"}:
            valid = value.replace("\u00b0", "").isascii()
        else:
            valid = value.isascii()
        if not valid:
            raise ConfigError("Message contains non-English characters")
    return fields


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
    """仅 LIVE Both daily-both 等待；预览 both 只记录；其他模式不做任何事。"""
    try:
        if hold_applies(mode):
            wait_for_send_time(os.getenv("DAILY_CLAIM_DATE"))
        elif mode == "dry-run" and os.getenv("LIVE_RECIPIENT") == "both":
            preview_hold()
    except Exception:
        print("send_hold=skipped reason=error", file=sys.stderr)


def main() -> int:
    mode = resolve_send_mode()
    raw_slot = _env("PUSH_SLOT")
    slot = raw_slot.lower() if raw_slot else "us"
    try:
        validate_send_context(mode, raw_slot if mode == "live" else slot)
        recipients = validate_live_configuration() if mode == "live" else []
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2
    try:
        fields = build_payload_fields()
        template_data = build_template_data(fields)
        if any(
            template_data[key]["value"] != fields[key]
            for key in ("meet_days", "love_line")
        ):
            raise ValueError("Meeting or love line was not rendered intact")
    except SystemExit:
        raise
    except Exception:
        print("组装数据失败（详情已隐藏）", file=sys.stderr)
        return 1
    try:
        if (
            mode == "live"
            and os.getenv("LIVE_RECIPIENT") == "both"
            and local_today("Asia/Shanghai").isoformat() != os.getenv("DAILY_CLAIM_DATE")
        ):
            raise ConfigError("双人真发日期已变化，已停止发送")
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2
    apply_send_hold(mode)
    if mode == "dry-run":
        payload_preview = {
            "touser": "REDACTED",
            "template_id": "REDACTED",
            "data": template_data,
            "meta": {
                "push_slot": slot,
                "send_mode": mode,
                "qweather_key_set": bool(os.getenv("QWEATHER_API_KEY")),
                "qweather_host_set": bool(os.getenv("QWEATHER_API_HOST")),
                "deepseek_key_set": bool(os.getenv("DEEPSEEK_API_KEY")),
            },
        }
        print(json.dumps(payload_preview, ensure_ascii=False, indent=2, sort_keys=True))
        print("SEND_MODE=dry-run：已跳过发送。")
        return 0
    for role, openid in recipients:
        try:
            result = send_template(openid, template_data)
            safe_result = {
                "ok": True,
                "errcode": result.get("errcode") if isinstance(result, dict) else None,
                "msgid": result.get("msgid") if isinstance(result, dict) else None,
            }
            if len(recipients) == 2:
                safe_result["recipient"] = role
            print(json.dumps(safe_result, ensure_ascii=False, sort_keys=True))
        except Exception:
            role_note = f"（收件角色：{role}）" if len(recipients) == 2 else ""
            print(f"发送失败（详情已脱敏）{role_note}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
