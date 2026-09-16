"""Locally edit one Shanghai-day override without persisting its text."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from daily_content import DailyContentError, validate_inputs  # noqa: E402


REPOSITORY = "carloshuangspec/wechat-ldr-daily-push"
SECRET = "DAILY_MESSAGE_CONFIG"


def today_shanghai() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _save(config: dict[str, str]) -> int:
    try:
        result = subprocess.run(
            ["gh", "secret", "set", SECRET, "-R", REPOSITORY, "--app", "actions"],
            input=json.dumps(config, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        print("Could not update the GitHub Secret. No update confirmed.")
        return 1
    if result.returncode != 0:
        print("Could not update the GitHub Secret. No update confirmed.")
        return 1
    print(f"Updated GitHub Secret: {SECRET}")
    return 0


def _clear() -> int:
    if input(f"Delete only {SECRET}? Type y to confirm: ").strip().lower() != "y":
        print("Cancelled; no Secret changed.")
        return 0
    try:
        result = subprocess.run(
            ["gh", "secret", "delete", SECRET, "-R", REPOSITORY, "--app", "actions"],
            text=True,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        print("Could not delete the GitHub Secret. No deletion confirmed.")
        return 1
    if result.returncode != 0:
        print("Could not delete the GitHub Secret. No deletion confirmed.")
        return 1
    print(f"Deleted GitHub Secret: {SECRET}")
    return 0


def main() -> int:
    try:
        default_day = today_shanghai()
        entered_day = input(f"Shanghai date [{default_day}] (or clear): ").strip()
        if entered_day.lower() == "clear":
            return _clear()
        day = entered_day or default_day
        theme = input("Optional theme for DeepSeek: ")
        exact = input("Optional exact English line (takes priority): ")
        try:
            config = validate_inputs(day, theme, exact)
        except DailyContentError:
            print("Invalid date or text. Nothing was saved.")
            return 1

        print(f"Date: {config['date']}")
        if "theme" in config:
            print(f"Theme: {config['theme']}")
        if "exact" in config:
            print(f"Exact line: {config['exact']}")
        if input("Save this one-day content? Type y to confirm: ").strip().lower() != "y":
            print("Cancelled; no Secret changed.")
            return 0
        return _save(config)
    except (KeyboardInterrupt, EOFError):
        print("Cancelled; no update confirmed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
