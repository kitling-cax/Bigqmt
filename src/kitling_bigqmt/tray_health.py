"""Fail-closed, read-only health checks used by BigQMT Tray.

The checker deliberately does not start a process and does not call QMT RPC.
Redis is probed with PING only; a failed or incomplete check never enables an
order path.  Production-readonly is kept separate from simulation so a
simulation status page cannot be presented as a formal-account health page.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .redis_resp import RedisRespClient
from .runtime_control import RuntimeControl
from .state_store import RuntimeStateStore
from . import machine_config


def _check(name: str, status: str, detail: str = "") -> dict[str, str]:
    value = {"name": name, "status": status}
    if detail:
        value["detail"] = detail
    return value


def _redis_health(config: dict[str, Any], timeout: float, attempts: int = 2) -> dict[str, str]:
    redis = dict(config.get("redis") or {})
    last_error = ""
    for attempt in range(max(1, int(attempts))):
        try:
            reply = RedisRespClient(timeout=timeout, **redis).command("PING")
            return _check("redis", "PASS" if reply == "PONG" else "FAIL", f"reply={reply!r}; attempts={attempt + 1}")
        except (OSError, ValueError, RuntimeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
    return _check("redis", "FAIL", f"{last_error}; attempts={max(1, int(attempts))}")


def _dashboard_health(profile: str, port: int, timeout: float, attempts: int = 2) -> dict[str, str]:
    last_error = ""
    for attempt in range(max(1, int(attempts))):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/healthz", timeout=timeout) as response:
                body = response.read().decode("utf-8", "replace")
            payload = json.loads(body)
            passed = response.status == 200 and payload.get("read_only") is True and payload.get("profile") == profile
            return _check("dashboard", "PASS" if passed else "FAIL", f"status={response.status}; attempts={attempt + 1}")
        except (OSError, urllib.error.URLError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
    return _check("dashboard", "FAIL", f"{last_error}; attempts={max(1, int(attempts))}")


def snapshot_freshness(config: dict[str, Any]) -> dict[str, Any]:
    """Measure only the persisted Bridge snapshot age; never call QMT or Redis.

    The tray status line needs the age itself, not just a pass/fail verdict,
    so an operator can see a stalled hourly snapshot before anyone runs a
    full health check.  This is deliberately the same measurement used by the
    ``bridge_snapshot`` health check: one code path, two presentations.
    """
    state_path = config.get("state_db")
    if not isinstance(state_path, str) or not state_path:
        return {"status": "DEFERRED", "detail": "state_db is not configured"}
    try:
        store = RuntimeStateStore(Path(state_path), Path(config.get("audit_dir") or Path(state_path).parent / "audit"))
        latest = store.latest_snapshot_bundle()
        metadata = store.latest_snapshot_metadata()
        if latest is None or metadata is None:
            return {"status": "DEGRADED", "detail": "no persisted Bridge snapshot"}
        captured = str(metadata.get("completed_at") or "")
        try:
            observed = datetime.fromisoformat(captured.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            age_seconds = max(0.0, (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds())
        except ValueError:
            return {"status": "DEGRADED",
                    "detail": f"latest_run_id={latest[0]}; invalid completed_at={captured!r}"}
        # Account/position snapshots are intentionally hourly for the daily
        # v1.1.15 strategy.  Allow one full interval plus a 15-minute margin;
        # a shorter threshold would mark a healthy hourly scheduler degraded
        # during the normal tail of each hour.
        max_age = float(config.get("bridge_snapshot_max_age_seconds", 4500))
        detail = f"latest_run_id={latest[0]}; age_seconds={age_seconds:.0f}; max_age_seconds={max_age:.0f}"
        return {
            "status": "PASS" if age_seconds <= max_age else "DEGRADED",
            "detail": detail,
            "latest_run_id": latest[0],
            "observed_at": observed.astimezone(timezone.utc).isoformat(),
            "age_seconds": round(age_seconds, 1),
            "max_age_seconds": max_age,
            "fresh": age_seconds <= max_age,
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"}


def _bridge_snapshot_health(config: dict[str, Any]) -> dict[str, str]:
    """Check only the persisted Bridge snapshot; never call QMT or Redis."""
    result = snapshot_freshness(config)
    return _check("bridge_snapshot", result["status"], result.get("detail", ""))


def check_profile(root: Path, profile: str, dashboard_port: int = 17890, timeout: float = 0.8, attempts: int = 2) -> dict[str, Any]:
    """Return an explainable health snapshot without enabling any capability."""
    if profile not in {"simulation", "production_readonly"}:
        raise ValueError("unsupported profile")
    root = Path(root).resolve()
    config_path = root / "config" / f"host_gateway.{('simulation' if profile == 'simulation' else 'production_readonly')}.json"
    control_path = root / "runtime_data" / "control" / profile / "runtime_control.json"
    checks: list[dict[str, str]] = []
    checks.append(_check("project_root", "PASS" if root.is_dir() else "FAIL", str(root)))
    checks.append(_check("profile_config", "PASS" if config_path.is_file() else "FAIL", str(config_path)))
    config: dict[str, Any] = {}
    try:
        config = machine_config.load_gateway(root, profile)
        checks.append(_check("profile_config_json", "PASS"))
    except (OSError, json.JSONDecodeError) as exc:
        checks.append(_check("profile_config_json", "FAIL", f"{type(exc).__name__}: {exc}"))
    checks.append(_redis_health(config, timeout, attempts) if config else _check("redis", "BLOCKED", "profile config unavailable"))
    checks.append(_bridge_snapshot_health(config) if config else _check("bridge_snapshot", "BLOCKED", "profile config unavailable"))
    control = RuntimeControl(control_path, environment="simulation" if profile == "simulation" else "production").status()
    checks.append(_check("order_lock", "PASS" if control.get("orders_enabled") is False and control.get("execution_consumer_enabled") is False else "FAIL", control.get("mode", "unknown")))
    checks.append(_dashboard_health(profile, dashboard_port, timeout, attempts))
    failed = [item for item in checks if item["status"] in {"FAIL", "BLOCKED"}]
    deferred = [item for item in checks if item["status"] in {"DEFERRED", "DEGRADED"}]
    overall = "FAIL_CLOSED" if failed else ("DEGRADED" if deferred else "HEALTHY")
    return {
        "profile": profile,
        "overall": overall,
        "orders_enabled": False,
        "execution_consumer_enabled": False,
        "checks": checks,
    }
