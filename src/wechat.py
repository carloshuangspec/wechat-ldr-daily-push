"""微信测试号：获取 access_token 并发送模板消息。"""

from __future__ import annotations

import os
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
    return s[:limit - 3] + "..."


def build_template_data(fields: dict[str, Any]) -> dict[str, dict[str, str]]:
    """
    组装模板 data。字段名需与测试号模板一致：
    greeting, city_a, time_a, weather_a, city_b, time_b, weather_b,
    love_days, meet_days, love_line, weather_source
    """
    limits = {
        "greeting": 20,
        "city_a": 12,
        "time_a": 10,
        "weather_a": 16,
        "city_b": 12,
        "time_b": 10,
        "weather_b": 16,
        "love_days": 12,
        "meet_days": 12,
        "love_line": 64,
        "weather_source": 120,
    }
    out: dict[str, dict[str, str]] = {}
    for key, limit in limits.items():
        if key == "love_line":
            line = str(fields.get(key, ""))
            if len(line) > limit:
                raise ValueError("Love line exceeds template limit")
            out[key] = {"value": line}
        else:
            out[key] = {"value": _short(fields.get(key, ""), limit)}
    return out


def inspect_template_fields(
    template_id: str | None = None, access_token: str | None = None
) -> dict[str, Any]:
    """Inspect only field presence for the configured template; return no IDs/content."""
    selected_id = (template_id or os.getenv("WECHAT_TEMPLATE_ID") or "").strip()
    if not selected_id:
        raise WeChatAPIError("缺少微信模板配置")
    token = access_token or get_access_token()
    try:
        response = requests.get(
            TEMPLATE_LIST_URL,
            params={"access_token": token},
            timeout=10.0,
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 200:
            raise WeChatAPIError("微信模板列表响应未被接受")
        body = _safe_json(response)
    except requests.RequestException:
        raise WeChatAPIError("微信模板列表请求失败") from None

    templates = body.get("template_list")
    if not isinstance(templates, list) or not all(isinstance(t, dict) for t in templates):
        raise WeChatAPIError("微信模板列表响应未被接受")
    matches = [t for t in templates if t.get("template_id") == selected_id]
    if not matches:
        return {"template_found": False, "missing_fields": []}
    if len(matches) != 1 or not isinstance(matches[0].get("content"), str):
        raise WeChatAPIError("微信模板列表响应未被接受")

    content = matches[0]["content"]
    missing = [
        name for name in build_template_data({})
        if "{{" + name + ".DATA}}" not in content
    ]
    return {"template_found": True, "missing_fields": missing}


def send_template(
    openid: str,
    template_id: str | None = None,
    data: dict[str, Any] | None = None,
    access_token: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    openid = str(openid or "").strip()
    if not openid:
        raise ValueError("缺少接收方 OPENID")
    template_id = (template_id or os.getenv("WECHAT_TEMPLATE_ID") or "").strip()
    if not template_id:
        raise ValueError("缺少 WECHAT_TEMPLATE_ID")
    if data is None:
        raise ValueError("缺少模板 data")
    token = access_token or get_access_token()
    payload = {
        "touser": openid,
        "template_id": template_id,
        "data": build_template_data(data)
        if not all(isinstance(v, dict) and "value" in v for v in data.values())
        else data,
    }
    try:
        r = requests.post(
            SEND_URL,
            params={"access_token": token},
            json=payload,
            timeout=timeout,
            allow_redirects=False,
        )
        r.raise_for_status()
        if r.status_code != 200:
            raise WeChatAPIError("微信模板响应未被接受")
        result = _safe_json(r)
    except requests.RequestException:
        raise WeChatAPIError("微信模板请求失败") from None
    errcode = result.get("errcode")
    msgid = result.get("msgid")
    errmsg = result.get("errmsg")
    msgid_text = (
        str(msgid).strip()
        if not isinstance(msgid, bool) and isinstance(msgid, (int, str))
        else ""
    )
    valid_msgid = (
        msgid_text.isascii()
        and msgid_text.isdigit()
        and int(msgid_text) > 0
    )
    if (
        type(errcode) is not int
        or errcode != 0
        or not valid_msgid
        or (errmsg is not None and errmsg != "ok")
    ):
        raise WeChatAPIError("微信模板响应未被接受")
    return {"errcode": 0, "msgid": msgid_text}
