"""Generate a short English love line, with a safe static fallback."""

from __future__ import annotations

import os
import random
import sys
from datetime import date

import requests

FALLBACK_LINES = [
    "Thinking of you",
    "Always by your side",
    "Love across miles",
    "You are my sunshine",
    "Closer every day",
    "See you soon, love",
    "Wish I were there",
    "My heart is with you",
    "Another day, my love",
    "Sending you a hug",
    "Good morning, love",
    "Only you, always",
]


def _fallback() -> str:
    # 按日期稳定一点，避免同日乱跳；再加一点随机
    idx = (date.today().toordinal() + random.randint(0, 2)) % len(FALLBACK_LINES)
    print("gemini_source=fallback", file=sys.stderr)
    return FALLBACK_LINES[idx]


def generate_love_line(timeout: float = 15.0) -> str:
    """Ask for a short English line, falling back for unusable responses."""
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return _fallback()

    model = (os.getenv("GEMINI_MODEL") or "gemini-3.8-flash").strip()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    prompt = (
        "Write one warm, natural good-morning line for my long-distance partner. "
        "English only, at most 20 characters including spaces. "
        "No quotes or explanations; output only the line."
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "thinkingConfig": {"thinkingLevel": "low"},
            "maxOutputTokens": 512,
        },
    }
    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": api_key},
            json=payload,
            timeout=timeout,
            allow_redirects=False,
        )
        if response.status_code != 200:
            return _fallback()
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return _fallback()
        candidate = candidates[0]
        if candidate.get("finishReason") != "STOP":
            return _fallback()
        parts = (candidate.get("content") or {}).get("parts") or []
        if not parts:
            return _fallback()
        line = (parts[0].get("text") or "").strip()
        line = line.strip("\"'").split("\n")[0].strip()
        if not line or len(line) > 20 or not line.isascii() or not line.isprintable():
            return _fallback()
        print("gemini_source=generated", file=sys.stderr)
        return line
    except (
        requests.RequestException,
        ValueError,
        KeyError,
        IndexError,
        AttributeError,
        TypeError,
    ):
        return _fallback()
