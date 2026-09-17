"""Verify the M01 machine.local.json single-point override gate.

Read-only: validates config/machine.local.json, renders both effective configs,
computes stable hashes, and inventories hardcoded local paths/ports. Never calls
QMT, Redis, or any order path.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from kitling_bigqmt import machine_config as mc  # noqa: E402


def _summary(cfg: dict) -> dict:
    return {
        "environment": cfg["environment"],
        "orders_enabled": cfg["orders_enabled"],
        "redis": cfg["redis"],
        "dashboard_port": cfg["dashboard_port"],
        "ready_port": cfg["ready_port"],
        "qmt_root": cfg["qmt_root"],
        "bin_x64": cfg["bin_x64"],
        "data_directory": cfg["data_directory"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence-dir", default=None)
    args = ap.parse_args(argv)

    root = mc.project_root()
    errors = mc.validate_machine_local(root)

    # Runtime loaders are fail-closed: a present-but-malformed machine.local.json
    # raises MachineLocalConfigError instead of silently falling back. The verify
    # gate must surface that as a validation error rather than a traceback.
    sim = None
    prod = None
    sim_hash = None
    prod_hash = None
    try:
        sim = mc.effective_config(root, "simulation")
        prod = mc.effective_config(root, "production_readonly")
        sim_hash = mc.effective_config_hash(root, "simulation")
        prod_hash = mc.effective_config_hash(root, "production_readonly")
    except mc.MachineLocalConfigError as exc:
        errors.append("machine.local loader fail-closed: %s" % exc)

    audit = mc.audit_hardcoded_paths(root)

    payload = {
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "scope": "M01 single-point machine.local.json override gate (read-only)",
        "machine_local_valid": not errors,
        "machine_local_validation": errors,
        "effective_config_hash": (
            {"simulation": sim_hash, "production_readonly": prod_hash}
            if sim is not None and prod is not None
            else None
        ),
        "effective_config_summary": (
            {"simulation": _summary(sim), "production_readonly": _summary(prod)}
            if sim is not None and prod is not None
            else None
        ),
        "hardcoded_audit": {
            "scanned": audit["scanned"],
            "finding_count": audit["finding_count"],
        },
        "readonly": True,
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.evidence_dir:
        out = Path(args.evidence_dir)
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%dT%H%M%S%z")
        dest = out / f"machine_local_gate_{stamp}.json"
        dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"evidence: {dest}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
