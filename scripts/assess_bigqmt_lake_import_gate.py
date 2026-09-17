"""Assess the complete BigQMT lake-import gate without publishing anything."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _latest_release() -> Path:
    dirs = sorted((p for p in (ROOT / "runtime_data/candidates").glob("bigqmt_candidate_*") if p.is_dir()), key=lambda p: p.name)
    if not dirs:
        raise FileNotFoundError("no candidate release")
    return dirs[-1]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Assess BigQMT candidate lake-import gates, read-only")
    parser.add_argument("release_dir", nargs="?", type=Path)
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    args = parser.parse_args()
    release = (args.release_dir or _latest_release()).resolve()
    manifest = _load(release / "manifest.json")
    readiness = _load(release / "import_readiness.json")
    plan = _load(release / "raw_bronze_import_plan.json")
    dryrun = _load(ROOT / "runtime_data/publish_dryrun" / str(manifest["release_id"]) / "dryrun_publish_manifest.json")
    queue = _load(ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/lake_price_repair_queue_20260912.json")

    daily_rows = int(manifest["files"]["daily_raw_overlay"]["rows"])
    intraday_rows = int(manifest["files"]["intraday_raw_overlay"]["rows"])
    dryrun_daily = int(dryrun["tables"]["daily"]["rows"])
    dryrun_intraday = int(dryrun["tables"]["intraday"]["rows"])
    published_manifest_path = args.lake_root.resolve() / "bronze" / "_bigqmt_raw_releases" / str(manifest["release_id"]) / "publish_manifest.json"
    verification_path = ROOT / "runtime_data" / "evidence" / "simulation" / "raw_publish" / (str(manifest["release_id"]) + "_verification.json")
    published = published_manifest_path.is_file() and verification_path.is_file()
    verification = _load(verification_path) if verification_path.is_file() else {}
    gates = {
        "candidate_manifest": "PASSED" if manifest.get("mode") == "LOCAL_CANDIDATE_ONLY_NO_LAKE_WRITE" else "BLOCKED",
        "raw_import_readiness": "PASSED" if readiness.get("raw_bronze_import_ready") is True else "BLOCKED",
        "daily_count_roundtrip": "PASSED" if daily_rows == dryrun_daily and daily_rows > 0 else "BLOCKED",
        "intraday_count_roundtrip": "PASSED" if intraday_rows == dryrun_intraday and intraday_rows > 0 else "BLOCKED",
        "repair_queue_integrity": "PASSED" if queue.get("gates", {}).get("evidence_integrity") == "PASSED" else "BLOCKED",
        "isolated_publisher": "PASSED" if (ROOT / "scripts" / "publish_bigqmt_raw_overlay.py").is_file() else "BLOCKED",
        "legacy_direct_append": plan.get("gates", {}).get("legacy_direct_append", "BLOCKED"),
        "canonical_pit": "BLOCKED_PENDING_CANONICAL_FACTOR_CHAIN_AND_AVAILABLE_AT",
        "explicit_publish_approval": "PASSED_USER_APPROVAL" if published else "PENDING_USER_APPROVAL",
        "published_raw_roundtrip": "PASSED" if verification.get("all_checks_passed") is True else ("PENDING" if not published else "BLOCKED"),
        "published_tree_hash": "PASSED" if verification.get("tree_hash_match") is True else ("PENDING" if not published else "BLOCKED"),
        "staging_cleanup": "PASSED" if verification.get("staging_absent") is True else ("PENDING" if not published else "BLOCKED"),
    }
    raw_ready = all(gates[name] == "PASSED" for name in (
        "candidate_manifest", "raw_import_readiness", "daily_count_roundtrip", "intraday_count_roundtrip", "repair_queue_integrity", "isolated_publisher"
    ))
    result = {
        "schema_version": 1,
        "kind": "bigqmt_complete_lake_import_gate",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "ISOLATED_RAW_COPY_ON_WRITE_PUBLISHED" if published else "READ_ONLY_NO_LAKE_WRITE",
        "release_id": manifest.get("release_id"),
        "release_dir": str(release),
        "published_target": str(published_manifest_path.parent) if published else None,
        "publish_manifest": str(published_manifest_path) if published else None,
        "verification_evidence": str(verification_path) if published else None,
        "counts": {
            "daily_valid_missing_candidates": daily_rows,
            "intraday_candidates": intraday_rows,
            "pre_listing_placeholders_quarantined": int(manifest["summary"].get("quarantined_pre_listing_rows", 0)),
            "repair_front_reclassification": int(queue["summary"].get("front_reclassification_candidates", 0)),
            "repair_unmatched_quarantine": int(queue["summary"].get("unmatched_quarantine_candidates", 0)),
        },
        "gates": gates,
        "decision": "PUBLISHED_ISOLATED_RAW_VERIFIED" if published and all(gates[name] == "PASSED" for name in ("published_raw_roundtrip", "published_tree_hash", "staging_cleanup")) else ("GO_FOR_EXPLICIT_RAW_PUBLISH_REVIEW" if raw_ready else "NO_GO"),
        "constraints": [
            "publish only to isolated canonical raw tables",
            "never append legacy bronze/bars_raw directly",
            "silver PIT remains blocked until canonical factor and available_at evidence",
            "no publish command is invoked by this gate",
        ],
        "safety": {
            "lake_write": bool(published),
            "global_latest_updated": False,
            "redis_write": False,
            "broker_call": False,
            "orders_enabled": False,
        },
    }
    output = release / "final_import_gate.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "decision": result["decision"], "gates": gates, "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0 if result["decision"] == "GO_FOR_EXPLICIT_RAW_PUBLISH_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
