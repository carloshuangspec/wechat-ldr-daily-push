"""和风天气：城市 geo 查询 + 实时天气。"""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_HOST = "https://devapi.qweather.com"


def _host() -> str:
    h = (os.getenv("QWEATHER_API_HOST") or DEFAULT_HOST).rstrip("/")
    if not h.startswith("http"):
        h = "https://" + h
    return h


def _key() -> str:
    return (os.getenv("QWEATHER_KEY") or "").strip()


def lookup_city(name: str, timeout: float = 10.0) -> dict[str, Any] | None:
    """按城市名查 LocationID；失败返回 None。"""
    key = _key()
    if not key:
        return None
    url = f"{_host()}/geo/v2/city/lookup"
    try:
        r = requests.get(url, params={"location": name, "key": key}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if str(data.get("code")) != "200":
            return None
        locs = data.get("location") or []
        if not locs:
            return None
        return locs[0]
    except (requests.RequestException, ValueError, KeyError):
        return None


def weather_now(location_id: str, timeout: float = 10.0) -> dict[str, Any] | None:
    """实时天气 now。"""
    key = _key()
    if not key:
        return None
    url = f"{_host()}/v7/weather/now"
    try:
        r = requests.get(
            url, params={"location": location_id, "key": key}, timeout=timeout
        )
        r.raise_for_status()
        data = r.json()
        if str(data.get("code")) != "200":
            return None
        return data.get("now")
    except (requests.RequestException, ValueError, KeyError):
        return None


def brief_weather(city_name: str) -> str:
    """
    返回简短天气文案，如「晴 12°C」。
    无 key / 请求失败时返回「天气暂不可用」。
    """
    if not _key():
        return "天气暂不可用"
    loc = lookup_city(city_name)
    if not loc:
        return "天气暂不可用"
    loc_id = loc.get("id")
    if not loc_id:
        return "天气暂不可用"
    now = weather_now(str(loc_id))
    if not now:
        return "天气暂不可用"
    text = (now.get("text") or "").strip() or "—"
    temp = now.get("temp")
    if temp is not None and str(temp) != "":
        return f"{text} {temp}°C"
    return text
