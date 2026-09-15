"""和风天气：城市 geo 查询 + 实时天气。"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import requests

UNAVAILABLE_CONFIG = "QWeather 配置不完整"
UNAVAILABLE_REQUEST = "QWeather 请求失败"


def _host() -> str:
    raw = (os.getenv("QWEATHER_API_HOST") or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlsplit(raw)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".qweatherapi.com")
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return f"https://{hostname}"


def _key() -> str:
    return (os.getenv("QWEATHER_KEY") or "").strip()


def lookup_city(name: str, timeout: float = 10.0) -> dict[str, Any] | None:
    """按城市名查 LocationID；失败返回 None。"""
    key = _key()
    host = _host()
    if not key or not host:
        return None
    url = f"{host}/geo/v2/city/lookup"
    try:
        r = requests.get(
            url,
            params={"location": name},
            headers={"X-QW-Api-Key": key},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return None
        if str(data.get("code")) != "200":
            return None
        locs = data.get("location")
        if not isinstance(locs, list) or not locs or not isinstance(locs[0], dict):
            return None
        return locs[0]
    except (requests.RequestException, ValueError, KeyError):
        return None


def weather_now(location_id: str, timeout: float = 10.0) -> dict[str, Any] | None:
    """实时天气 now。"""
    key = _key()
    host = _host()
    if not key or not host:
        return None
    url = f"{host}/v7/weather/now"
    try:
        r = requests.get(
            url,
            params={"location": location_id},
            headers={"X-QW-Api-Key": key},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return None
        if str(data.get("code")) != "200":
            return None
        now = data.get("now")
        return now if isinstance(now, dict) else None
    except (requests.RequestException, ValueError, KeyError):
        return None


def brief_weather(city_name: str) -> str:
    """
    返回简短天气文案，如「晴 12°C」。
    配置不完整或请求失败时返回不含敏感值的状态。
    """
    if not _key() or not _host():
        return UNAVAILABLE_CONFIG
    loc = lookup_city(city_name)
    if not loc:
        return UNAVAILABLE_REQUEST
    loc_id = loc.get("id")
    if not loc_id:
        return UNAVAILABLE_REQUEST
    now = weather_now(str(loc_id))
    if not now:
        return UNAVAILABLE_REQUEST
    text = str(now.get("text") or "").strip() or "—"
    temp = now.get("temp")
    if temp is not None and str(temp) != "":
        return f"{text} {temp}°C"
    return text
