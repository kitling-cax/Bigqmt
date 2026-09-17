"""Validate a MiniQMT embedded-Python CSV export on the host.

This command is intentionally a candidate-only step: it normalizes and validates
the export but never writes Parquet, updates a lake pointer, or calls QMT/Redis.
Volume and amount units must be supplied from an observed measurement.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Allow direct ``py scripts/...`` execution from a checkout without installing
# the package first.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.lake_ingest_v2 import BronzeIngestError, normalize_miniqmt, validate_bronze


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--volume-unit", required=True)
    parser.add_argument("--amount-unit", required=True)
    parser.add_argument("--source-release", default="miniqmt_embedded_probe")
    args = parser.parse_args()
    result = {
        "schema_version": 1,
        "kind": "miniqmt_host_import_validation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": str(args.input.resolve()),
        "source_release": args.source_release,
        "volume_unit": args.volume_unit,
        "amount_unit": args.amount_unit,
        "lake_write": False,
        "global_latest_updated": False,
        "orders_enabled": False,
        "broker_calls": False,
    }
    try:
        frame = pd.read_csv(args.input)
        normalized = normalize_miniqmt(
            frame,
            source_release=args.source_release,
            volume_unit=args.volume_unit,
            amount_unit=args.amount_unit,
            etf_codes={"510300.SH"},
        )
        result["validation"] = validate_bronze(normalized)
        result["status"] = "CANDIDATE_VALIDATED"
        result["codes"] = sorted(normalized["code"].unique().tolist())
        result["rows_by_code"] = normalized.groupby("code").size().astype(int).to_dict()
    except (BronzeIngestError, OSError, ValueError, KeyError) as exc:
        result["status"] = "BLOCKED_VALIDATION"
        result["error"] = str(exc)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
