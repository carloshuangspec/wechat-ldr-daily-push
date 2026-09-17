"""Fail-closed GitHub claim for a single Shanghai delivery day."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests


class ClaimError(Exception):
    """Raised when a delivery claim cannot be safely established."""


REPOSITORY = "carloshuangspec/wechat-ldr-daily-push"
API_ROOT = "https://api.github.com/repos/carloshuangspec/wechat-ldr-daily-push"
HEADERS_ACCEPT = "application/vnd.github+json"


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _validate(day: str, repo: str, sha: str, token: str, now: date | None) -> str:
    if now is not None and type(now) is not date:
        raise ClaimError("claim unavailable")
    today = now if now is not None else _today()
    if repo != REPOSITORY or not isinstance(day, str):
        raise ClaimError("claim unavailable")
    try:
        canonical_day = date.fromisoformat(day).isoformat()
    except (TypeError, ValueError):
        raise ClaimError("claim unavailable")
    if canonical_day != day or day != today.isoformat():
        raise ClaimError("claim unavailable")
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise ClaimError("claim unavailable")
    if not isinstance(token, str) or not token:
        raise ClaimError("claim unavailable")
    return f"refs/tags/ldr-daily-{day}"


def claim(day: str, repo: str, sha: str, token: str, *, http=requests,
          now: date | None = None) -> bool:
    ref = _validate(day, repo, sha, token, now)
    headers = {"Authorization": f"Bearer {token}", "Accept": HEADERS_ACCEPT}
    try:
        response = http.post(
            f"{API_ROOT}/git/refs", json={"ref": ref, "sha": sha},
            headers=headers, timeout=10, allow_redirects=False,
        )
        status = response.status_code
        if status == 201:
            if response.json().get("ref") == ref:
                return True
            raise ClaimError("claim unavailable")
        if status not in (409, 422):
            raise ClaimError("claim unavailable")
        response = http.get(
            f"{API_ROOT}/git/ref/tags/ldr-daily-{day}",
            headers=headers, timeout=10, allow_redirects=False,
        )
        if response.status_code == 200 and response.json().get("ref") == ref:
            return False
    except ClaimError:
        raise
    except (requests.RequestException, TimeoutError, ValueError, TypeError, AttributeError, KeyError):
        raise ClaimError("claim unavailable")
    raise ClaimError("claim unavailable")


def main() -> int:
    try:
        day = os.getenv("DELIVERY_DATE") or _today().isoformat()
        output_path = os.getenv("GITHUB_OUTPUT")
        if not output_path:
            raise ClaimError("claim unavailable")
        with open(output_path, "a", encoding="utf-8") as output:
            exists = not claim(
                day, os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_SHA", ""),
                os.getenv("GH_TOKEN", ""),
            )
            output.write(f"claimed={'false' if exists else 'true'}\nday={day}\n")
        print(f"daily_claim={'exists' if exists else 'created'} day={day}")
        return 0
    except Exception:
        print("daily_claim_failed", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
