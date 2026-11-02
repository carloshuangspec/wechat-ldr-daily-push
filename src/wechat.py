"""微信测试号：获取 access_token 并发送模板消息。"""

from __future__ import annotations

import os
import re
from typing import Any

import requests

TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/template/send"
TEMPLATE_LIST_URL = "https://api.weixin.qq.com/cgi-bin/template/get_all_private_template"


class WeChatAPIError(RuntimeError):
    """不携带请求参数、响应正文或凭据的微信 API 异常。"""


def _safe_json(response: requests.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        raise WeChatAPIError("微信 API 返回无效 JSON") from None
    if not isinstance(data, dict) or not data:
        raise WeChatAPIError("微信 API 返回空 JSON")
    return data


def get_access_token(
    app_id: str | None = None,
    app_secret: str | None = None,
    timeout: float = 10.0,
) -> str:
    app_id = (app_id or os.getenv("WECHAT_APP_ID") or "").strip()
    app_secret = (app_secret or os.getenv("WECHAT_APP_SECRET") or "").strip()
    if not app_id or not app_secret:
        raise ValueError("缺少 WECHAT_APP_ID 或 WECHAT_APP_SECRET")
    try:
        r = requests.get(
            TOKEN_URL,
            params={
                "grant_type": "client_credential",
                "appid": app_id,
                "secret": app_secret,
            },
            timeout=timeout,
            allow_redirects=False,
        )
        r.raise_for_status()
        if r.status_code != 200:
            raise WeChatAPIError("微信 token 响应未被接受")
        data = _safe_json(r)
    except requests.RequestException:
        raise WeChatAPIError("微信 token 请求失败") from None
    token = data.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise WeChatAPIError("微信 token 响应未被接受")
    return token.strip()


def _short(value: Any, limit: int = 20) -> str:
    s = str(value if value is not None else "")
    if len(s) <= limit:
        return s
    return s[:limit] + "..."


def _extract_send_error(data: dict[str, Any]) -> str:
    code = data.get("errcode")
    msg = data.get("errmsg")
    if code in (None, 0) and msg in (None, "ok"):
        return ""
    return f"微信发送失败：errcode={_short(code)} errmsg={_short(msg)}"


def send_template_message(
    access_token: str,
    openid: str,
    template_id: str,
    data: dict[str, Any],
    timeout: float = 10.0,
) -> dict[str, Any]:
    """发送一条微信模板消息；仅返回简短的错误摘要，绝不记录消息正文。"""
    if not isinstance(access_token, str) or not access_token.strip():
        raise ValueError("缺少微信 access_token")
    if not isinstance(openid, str) or not openid.strip():
        raise ValueError("缺少微信 openid")
    if not isinstance(template_id, str) or not template_id.strip():
        raise ValueError("缺少微信模板 ID")
    try:
        r = requests.post(
            SEND_URL,
            params={"access_token": access_token.strip()},
            json={
                "touser": openid.strip(),
                "template_id": template_id.strip(),
                "data": data,
            },
            timeout=timeout,
            allow_redirects=False,
        )
        r.raise_for_status()
        if r.status_code != 200:
            raise WeChatAPIError("微信发送响应未被接受")
        result = _safe_json(r)
    except requests.RequestException:
        raise WeChatAPIError("微信发送请求失败") from None
    err = _extract_send_error(result)
    if err:
        raise WeChatAPIError(err)
    return result


def _split_template_fields(data: dict[str, Any]) -> dict[str, Any]:
    """将模板的 data 对象拆分为字段名与 value；仅保留字符串值。"""
    fields: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(value.get("value"), str):
            fields[key] = value["value"]
    return fields


def inspect_template(data: dict[str, Any]) -> dict[str, Any]:
    """从模板消息的 data 中提取字段信息；不记录消息正文。"""
    fields = _split_template_fields(data)
    meta = {}
    for key in sorted(fields):
        value = fields[key]
        meta[key] = {"length": len(value), "line_count": value.count("\n") + 1}
    return meta


# 模板字段长度上限（按微信模板消息的字段限制设置）。
# love_line 已放宽到 200：生成内容的安全上限，特殊日的短诗全文放这里；
# meet_days 仍为 64，放不下全文时 main 只放倒计时。
FIELD_LIMITS = {
    "date": 32,
    "known_days": 16,
    "love_days": 16,
    "love_line": 200,
    "meet_days": 64,
    "weather_a": 64,
    "weather_b": 64,
    "weather_source": 32,
}


def build_template_data(
    date_label: str,
    known_days: int,
    love_days: int,
    love_line: str,
    meet_days: str,
    weather_a: str,
    weather_b: str,
    weather_source: str,
) -> dict[str, Any]:
    """组装模板消息 data；每个字段仅接受非空文本；空值会被忽略。"""
    raw = {
        "date": date_label,
        "known_days": str(known_days),
        "love_days": str(love_days),
        "love_line": love_line,
        "meet_days": meet_days,
        "weather_a": weather_a,
        "weather_b": weather_b,
        "weather_source": weather_source,
    }
    fields: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(value, str) or not value:
            continue
        limit = FIELD_LIMITS.get(key)
        if limit is not None and len(value) > limit:
            raise ValueError(f"模板字段 {key} 超出长度上限")
        fields[key] = {"value": value}
    return fields


def send_template(payload: dict[str, Any]) -> str:
    """按模板发送给两位收件人；任一失败即整体失败，不做部分重试。"""
    template_id = (os.getenv("WECHAT_TEMPLATE_ID") or "").strip()
    openid_cn = (os.getenv("WECHAT_OPENID_CN") or "").strip()
    openid_self = (os.getenv("WECHAT_OPENID_SELF") or "").strip()
    if not template_id:
        raise ValueError("缺少 WECHAT_TEMPLATE_ID")
    if not openid_cn or not openid_self:
        raise ValueError("缺少微信收件人 openid")
    token = get_access_token()
    for openid in (openid_cn, openid_self):
        send_template_message(token, openid, template_id, payload)
    return "sent"
