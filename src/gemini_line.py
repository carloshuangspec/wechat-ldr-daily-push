"""Gemini 生成一句短中文情话；失败回退静态列表。"""

from __future__ import annotations

import os
import random
from datetime import date

import requests

FALLBACK_LINES = [
    "想你的心，比时差更准时。",
    "今天也隔着屏幕抱抱你。",
    "距离很远，心意很近。",
    "等风，也等你。",
    "你是我一天里最想分享的天气。",
    "早安，世界另一头的你。",
    "倒计时再短一点也好。",
    "想听你说今天过得怎样。",
    "星星替我陪着你。",
    "再忙也记得喝水，也记得被爱。",
    "有你的日子，都算好日子。",
    "晚一点也好，总会再见。",
]


def _fallback() -> str:
    # 按日期稳定一点，避免同日乱跳；再加一点随机
    idx = (date.today().toordinal() + random.randint(0, 2)) % len(FALLBACK_LINES)
    return FALLBACK_LINES[idx]


def generate_love_line(timeout: float = 15.0) -> str:
    """调用 Gemini 生成一句短中文情话；失败则用静态列表。"""
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return _fallback()

    model = (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    prompt = (
        "写一句给异地恋对象的早安情话，中文，不超过20个字，"
        "温馨自然，不要引号，不要解释，只输出这一句。"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 64,
        },
    }
    try:
        r = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return _fallback()
        parts = (candidates[0].get("content") or {}).get("parts") or []
        if not parts:
            return _fallback()
        text = (parts[0].get("text") or "").strip()
        # 去掉引号与过长内容
        text = text.strip("「」『』\"'").split("\n")[0].strip()
        if not text or len(text) > 40:
            return _fallback()
        return text
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return _fallback()
