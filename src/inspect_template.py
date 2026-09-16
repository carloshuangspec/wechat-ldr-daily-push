"""Read-only template diagnostic for a restricted GitHub Actions workflow."""

from __future__ import annotations

import json
import os
import sys

from wechat import inspect_template_fields


def main() -> int:
    try:
        result = inspect_template_fields(os.getenv("WECHAT_TEMPLATE_ID"))
    except Exception:
        print("template_check_failed", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0 if result["template_found"] and not result["missing_fields"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
