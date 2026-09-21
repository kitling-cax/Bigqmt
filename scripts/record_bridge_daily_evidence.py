"""Persist one daily BIGQMT_BRIDGE running-evidence record per Tray profile.

The bridge strategy source is frozen inside QMT, so the durable proof that the
expected build is the one actually running is what the bridge itself answers:
the allow-listed ``ping`` RPC returns the bridge version and RPC revision, and
the persisted account snapshot proves the same bridge is completing real
read-only work.  This script records both, once per day, beside the other
read-only evidence so a later audit can see the version that was running on a
given date instead of relying on a memory of a health check.

Read-only and fail-closed: exactly one ping RPC plus local file reads.  It
never arms, claims, submits, or cancels anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt import machine_config  # noqa: E402
from kitling_bigqmt.bridge_probe import probe_bridge_ping  # noqa: E402
from kitling_bigqmt.runtime_control import RuntimeControl  # noqa: E402
from kitling_bigqmt.tray_health import snapshot_freshness  # noqa: E402

SCHEMA_VERSION = 1
# One sample per supervisor attempt; the day only needs a handful, and the cap
# keeps a retry storm from growing the evidence file without bound.
MAX_SAMPLES_PER_DAY = 96


def evidence_directory(profile: str) -> Path:
    return ROOT / "runtime_data" / "evidence" / profile / "bridge_daily"


def order_lock_state(profile: str) -> dict[str, Any]:
    control_path = ROOT / "runtime_data" / "control" / profile / "runtime_control.json"
    environment = "simulation" if profile == "simulation" else "production"
    status = RuntimeControl(control_path, environment=environment).status()
    return {
        "mode": status.get("mode", "unknown"),
        "orders_enabled": status.get("orders_enabled") is True,
        "execution_consumer_enabled": status.get("execution_consumer_enabled") is True,
    }


def build_sample(profile: str, config: dict[str, Any], ping_timeout: float) -> dict[str, Any]:
    observed_at = datetime.now(timezone.utc)
    ping = probe_bridge_ping(config, ping_timeout)
    reply = ping.get("bridge_reply") or {}
    version = str(reply.get("version") or "")
    rpc_revision = str(reply.get("rpc_revision") or "")
    reported_account = str(reply.get("account_id") or "")
    expected_account = str(config.get("account_id") or "")
    freshness = snapshot_freshness(config)
    lock = order_lock_state(profile)
    checks = {
        "bridge_ping": ping["status"],
        "bridge_version_reported": "PASS" if version else "DEGRADED",
        "bridge_revision_reported": "PASS" if rpc_revision else "DEGRADED",
        "account_match": "PASS" if reported_account and reported_account == expected_account else "FAIL",
        # A stale snapshot is a scheduling symptom, not a liveness failure: the
        # live ping above is the authority on whether the bridge is running.
        "snapshot_fresh": "PASS" if freshness.get("fresh") else str(freshness.get("status", "DEGRADED")),
        # A simulation run may intentionally keep the local execution switch
        # enabled for unattended operation.  It is valid when the persistent
        # mode is explicit; formal profiles must remain locked.
        "order_lock": (
            "PASS" if (
                (profile == "simulation" and lock["mode"] == "SIMULATION_STRATEGY_EXECUTION_ENABLED"
                 and lock["orders_enabled"] and lock["execution_consumer_enabled"])
                or (profile != "simulation" and lock["orders_enabled"] is False)
                or lock["mode"] == "READ_ONLY_LOCKED"
            ) else "FAIL"
        ),
    }
    if checks["bridge_ping"] != "PASS":
        status = "BLOCKED"
    elif all(value == "PASS" for value in checks.values()):
        status = "PASSED"
    else:
        status = "DEGRADED"
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "environment": config.get("environment"),
        "account_id": expected_account,
        "bridge_strategy": "BIGQMT_BRIDGE",
        "status": status,
        "checks": checks,
        "checked_at_utc": observed_at.isoformat(),
        "checked_at_local": observed_at.astimezone().isoformat(),
        "bridge_version": version,
        "rpc_revision": rpc_revision,
        "bridge_server_time": str(reply.get("server_time") or ""),
        "bridge_account_type": str(reply.get("account_type") or ""),
        "bridge_allow_order_methods": reply.get("allow_order_methods"),
        "bridge_latency_ms": ping.get("latency_ms"),
        "strategy_running_evidence": (
            "ping pong; version=%s; rpc_revision=%s" % (version or "UNKNOWN", rpc_revision or "UNKNOWN")
            if checks["bridge_ping"] == "PASS"
            else "ping failed: %s" % ping.get("detail", "")
        ),
        "bridge_ping": ping,
        "snapshot": freshness,
        "order_lock": lock,
        "read_only": not (profile == "simulation" and lock["orders_enabled"]),
        "broker_call_made": False,
        "orders_enabled": bool(lock["orders_enabled"]),
    }


def write_sample(profile: str, sample: dict[str, Any]) -> Path:
    directory = evidence_directory(profile)
    directory.mkdir(parents=True, exist_ok=True)
    trading_date = datetime.now().strftime("%Y-%m-%d")
    path = directory / ("bridge_daily_%s.json" % trading_date.replace("-", ""))
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "environment": sample.get("environment"),
        "account_id": sample.get("account_id"),
        "bridge_strategy": "BIGQMT_BRIDGE",
        "trading_date": trading_date,
        "read_only": bool(sample.get("read_only", True)),
        "orders_enabled": bool(sample.get("orders_enabled", False)),
        "broker_call_made": False,
        "samples": [],
    }
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                document.update({key: existing[key] for key in ("samples",) if key in existing})
        except (OSError, json.JSONDecodeError):
            # A corrupt file is replaced rather than merged; the new sample is
            # still written so the day is never left without evidence.
            document["samples"] = []
    samples = [item for item in document.get("samples") or [] if isinstance(item, dict)]
    samples.append(sample)
    document["samples"] = samples[-MAX_SAMPLES_PER_DAY:]
    document["sample_count"] = len(document["samples"])
    document["last_status"] = sample["status"]
    document["last_checked_at_utc"] = sample["checked_at_utc"]
    document["latest"] = sample
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Record daily BIGQMT_BRIDGE running evidence.")
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    try:
        config = machine_config.load_gateway(ROOT, args.profile)
        sample = build_sample(args.profile, config, args.timeout)
        path = write_sample(args.profile, sample)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc),
                          "profile": args.profile, "broker_call_made": False}, ensure_ascii=False))
        return 2
    print(json.dumps({
        "status": sample["status"],
        "profile": args.profile,
        "bridge_version": sample["bridge_version"],
        "rpc_revision": sample["rpc_revision"],
        "checks": sample["checks"],
        "evidence": str(path),
        "broker_call_made": False,
        "orders_enabled": bool(sample.get("orders_enabled", False)),
    }, ensure_ascii=False, indent=2))
    return 0 if sample["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
