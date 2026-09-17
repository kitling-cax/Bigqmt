"""Run one read-only Coordinator shadow soak sample and append JSONL evidence."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def get_json(url: str, timeout: float) -> tuple[int, dict]:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - endpoint is operator supplied
        body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("response is not a JSON object")
        return int(response.status), body


def sample(authority: str, shadow: str, timeout: float) -> dict[str, object]:
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result: dict[str, object] = {
        "checked_at": checked_at,
        "authority": authority,
        "shadow": shadow,
        "readonly": True,
        "orders_enabled": False,
        "ok": True,
        "checks": {},
        "errors": [],
    }
    checks: dict[str, object] = result["checks"]  # type: ignore[assignment]
    errors: list[str] = result["errors"]  # type: ignore[assignment]
    for name, base, expected_mode in (
        ("authority", authority, None),
        ("shadow", shadow, "shadow_readonly"),
    ):
        try:
            status, ready = get_json(f"{base.rstrip('/')}/readyz", timeout)
            mode = ready.get("mode")
            passed = status == 200 and ready.get("status") == "ready"
            if expected_mode is not None:
                passed = passed and mode == expected_mode
            checks[f"{name}_readyz"] = {"status": status, "mode": mode, "passed": passed}
            if not passed:
                errors.append(f"{name} readyz failed")
        except (OSError, ValueError, URLError) as exc:
            checks[f"{name}_readyz"] = {"passed": False, "error": type(exc).__name__}
            errors.append(f"{name} readyz unavailable")

    try:
        status, progress = get_json(f"{shadow.rstrip('/')}/api/v1/progress", timeout)
        passed = status == 200 and progress.get("readonly") is True and progress.get("orders_enabled") is False
        checks["shadow_progress"] = {"status": status, "phase": progress.get("phase"), "passed": passed}
        if not passed:
            errors.append("shadow progress is not readonly")
    except (OSError, ValueError, URLError) as exc:
        checks["shadow_progress"] = {"passed": False, "error": type(exc).__name__}
        errors.append("shadow progress unavailable")

    result["ok"] = not errors
    result["orders_enabled"] = False
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority", default="http://192.0.2.121:18443")
    parser.add_argument("--shadow", default="http://192.0.2.121:18666")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = sample(args.authority, args.shadow, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
