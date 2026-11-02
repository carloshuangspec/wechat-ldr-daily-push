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
    if limit < 3:
        return s[:limit]
    return s[: limit - 3] + "..."


def _extract_send_error(data: dict[str, Any]) -> str:
    code = data.get("errcode")
    msg = data.get("errmsg")
    if code in (None, 0) and msg in (None, "ok"):
        return ""
    return f"微信发送失败：errcode={_short(code)} errmsg={_short(msg)}"


# 模板字段长度上限（按微信模板消息的字段限制设置）。
# love_line 已放宽到 200：生成内容的安全上限，特殊日的短诗全文放这里；
# meet_days 仍为 64，放不下全文时 main 只放倒计时。
FIELD_LIMITS = {
    "greeting": 20,
    "city_a": 12,
    "time_a": 10,
    "weather_a": 16,
    "city_b": 12,
    "time_b": 10,
    "weather_b": 16,
    "love_days": 12,
    "meet_days": 64,
    "love_line": 200,
    "weather_source": 120,
}


def build_template_data(fields: dict) -> dict:
    """组装模板消息 data；meet_days 与 love_line 超限即失败，其他字段截断。"""
    out: dict[str, Any] = {}
    for key, limit in FIELD_LIMITS.items():
        value = fields.get(key)
        if value is None:
            continue
        if key in ("meet_days", "love_line"):
            if len(str(value)) > limit:
                raise ValueError(f"Template field {key} exceeds limit")
            out[key] = {"value": str(value)}
            continue
        out[key] = {"value": _short(value, limit)}
    return out


def send_template(openid: str, data: dict) -> dict:
    """Send one template message; return only errcode/msgid on success."""
    token = get_access_token()
    template_id = (os.getenv("WECHAT_TEMPLATE_ID") or "").strip()
    if not template_id:
        raise ValueError("缺少 WECHAT_TEMPLATE_ID")
    try:
        response = requests.post(
            SEND_URL,
            params={"access_token": token},
            json={"touser": openid, "template_id": template_id, "data": data},
            timeout=10,
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 200:
            raise WeChatAPIError("微信发送响应未被接受")
        result = _safe_json(response)
    except requests.RequestException:
        raise WeChatAPIError("微信发送请求失败") from None
    err = _extract_send_error(result)
    if err:
        raise WeChatAPIError(err)
    return {"errcode": 0, "msgid": result.get("msgid")}


def inspect_template_fields(
    template_id: str | None = None, access_token: str | None = None
) -> dict:
    """Fetch one template's fields from WeChat; return only field names."""
    token = access_token or get_access_token()
    try:
        response = requests.get(
            TEMPLATE_LIST_URL,
            params={"access_token": token},
            timeout=10,
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 200:
            raise WeChatAPIError("微信模板列表响应未被接受")
        data = _safe_json(response)
    except requests.RequestException:
        raise WeChatAPIError("微信模板列表请求失败") from None
    templates = data.get("template_list")
    if not isinstance(templates, list):
        raise WeChatAPIError("微信模板列表响应无效")
    for item in templates:
        if not isinstance(item, dict):
            continue
        if template_id and item.get("template_id") != template_id:
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        return {name: True for name in re.findall(r"\{\{(\w+)\.DATA\}\}", content)}
    if template_id:
        raise WeChatAPIError("未找到指定模板")
    return {}
