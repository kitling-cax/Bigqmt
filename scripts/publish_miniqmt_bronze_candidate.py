"""Build/publish an isolated MiniQMT Bronze candidate (never updates LATEST)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.lake_ingest_v2 import APPROVAL_TOKEN, normalize_miniqmt, publish_bronze_candidate, validate_bronze  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    parser.add_argument("--release-id", default=None)
    parser.add_argument("--approve-publish", action="store_true")
    args = parser.parse_args()
    frame = pd.concat([pd.read_csv(path) for path in args.input], ignore_index=True)
    normalized = normalize_miniqmt(frame, source_release="miniqmt_embedded_20260912_u25", volume_unit="lots_measured", amount_unit="cny_measured")
    checks = validate_bronze(normalized)
    release_id = args.release_id or ("unified_v2_bronze_miniqmt_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    if not args.approve_publish:
        result = {"status": "READY_FOR_EXPLICIT_MINIQMT_BRONZE_PUBLISH", "release_id": release_id, "checks": checks, "global_latest_updated": False, "orders_enabled": False, "broker_calls": False}
    else:
        result = publish_bronze_candidate([normalized], release_id, args.lake_root, APPROVAL_TOKEN)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
