"""和风天气：城市 geo 查询 + 实时天气。"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlsplit

import requests

UNAVAILABLE_CONFIG = "Unavailable"
UNAVAILABLE_REQUEST = "Weather offline"
OPEN_METEO_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_SOURCE = (
    "Open-Meteo https://open-meteo.com | GeoNames | "
    "CC BY 4.0 https://creativecommons.org/licenses/by/4.0/ | adapted"
)
QWEATHER_SOURCE = "QWeather https://www.qweather.com"

WEATHER_CODES = {
    0: "Clear", 1: "Fair", 2: "Ptly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
    56: "Icy driz", 57: "Icy driz",
    61: "Rain", 63: "Rain", 65: "Rain", 66: "Icy rain", 67: "Icy rain",
    71: "Snow", 73: "Snow", 75: "Snow", 77: "Snow",
    80: "Showers", 81: "Showers", 82: "Showers",
    85: "Snow shwr", 86: "Snow shwr",
    95: "Storm", 96: "Hail storm", 99: "Hail storm",
}


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


def weather_source() -> str:
    """Attribute the provider actually selected for this run."""
    return QWEATHER_SOURCE if _key() and _host() else OPEN_METEO_SOURCE


def _open_meteo_get(url: str, params: dict[str, Any]) -> dict[str, Any] | None:
    try:
        response = requests.get(url, params=params, timeout=10, allow_redirects=False)
        response.raise_for_status()
        if response.status_code != 200:
            return None
        data = response.json()
        return data if isinstance(data, dict) else None
    except (requests.RequestException, ValueError):
        return None


def open_meteo_weather(city_name: str) -> str | None:
    """Keyless personal-use fallback with a bounded English result."""
    country = {"Ann Arbor": "US", "Shanghai": "CN"}.get(city_name)
    params: dict[str, Any] = {
        "name": city_name, "count": 1, "language": "en", "format": "json",
    }
    if country:
        params["countryCode"] = country
    geo = _open_meteo_get(OPEN_METEO_GEO_URL, params)
    results = geo.get("results") if geo else None
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return None
    location = results[0]
    if country and location.get("country_code") != country:
        return None
    latitude, longitude = location.get("latitude"), location.get("longitude")
    if not all(type(v) in (int, float) for v in (latitude, longitude)):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    forecast = _open_meteo_get(OPEN_METEO_FORECAST_URL, {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code",
        "temperature_unit": "celsius",
        "timezone": "auto",
    })
    current = forecast.get("current") if forecast else None
    if not isinstance(current, dict):
        return None
    code, temp = current.get("weather_code"), current.get("temperature_2m")
    if type(code) is not int or code not in WEATHER_CODES:
        return None
    if type(temp) not in (int, float) or not -100 <= temp <= 70:
        return None
    report = f"{WEATHER_CODES[code]} {round(temp)}°C"
    return report if len(report) <= 16 else None


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
            allow_redirects=False,
        )
        r.raise_for_status()
        if r.status_code != 200:
            return None
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
            params={"location": location_id, "lang": "en"},
            headers={"X-QW-Api-Key": key},
            timeout=timeout,
            allow_redirects=False,
        )
        r.raise_for_status()
        if r.status_code != 200:
            return None
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
    返回简短英文天气文案，如 "Sunny 12°C"。
    和风未配置时改用免密钥 Open-Meteo；失败返回不含敏感值的状态。
    """
    if not _key() or not _host():
        return open_meteo_weather(city_name) or UNAVAILABLE_CONFIG
    loc = lookup_city(city_name)
    if not loc:
        return UNAVAILABLE_REQUEST
    loc_id = loc.get("id")
    if not loc_id:
        return UNAVAILABLE_REQUEST
    now = weather_now(str(loc_id))
    if not now:
        return UNAVAILABLE_REQUEST
    text = str(now.get("text") or "").strip()
    if not text or not text.isascii() or not text.isprintable():
        return UNAVAILABLE_REQUEST
    temp = now.get("temp")
    if temp is not None and str(temp) != "":
        if not re.fullmatch(r"-?[0-9]+", str(temp)):
            return UNAVAILABLE_REQUEST
        result = f"{text} {temp}°C"
        if len(result) <= 16:
            return result
    return text if len(text) <= 16 else UNAVAILABLE_REQUEST
