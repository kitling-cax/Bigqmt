"""Build an explicit, non-backfilled Universe PIT candidate."""
from __future__ import annotations
import hashlib, json, os, shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pandas as pd


def build_membership_rows(codes: list[str], asset_class: str, effective_from: str,
                          available_at: str, source: str, release_id: str) -> pd.DataFrame:
    if not codes or not effective_from or not available_at:
        raise ValueError("codes, effective_from and available_at are required")
    parsed = pd.Timestamp(available_at)
    if parsed.tzinfo is None:
        raise ValueError("available_at must include timezone")
    rows = []
    for code in sorted({str(item).upper() for item in codes}):
        row = {"code": code, "asset_class": asset_class, "effective_from": effective_from,
               "effective_to": None, "available_at": parsed.isoformat(), "source": source,
               "release_id": release_id, "membership_status": "FORWARD_ONLY_EXPLICIT_START"}
        row["row_hash"] = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        rows.append(row)
    return pd.DataFrame(rows)


def validate_universe(frame: pd.DataFrame) -> dict[str, Any]:
    required = {"code", "asset_class", "effective_from", "effective_to", "available_at", "source", "row_hash"}
    missing = sorted(required - set(frame.columns))
    if missing: raise ValueError("Universe missing: %s" % ",".join(missing))
    if frame.empty or frame[["code", "effective_from"]].duplicated().any() or frame["row_hash"].duplicated().any():
        raise ValueError("Universe has empty or duplicate membership keys/hashes")
    if pd.to_datetime(frame["available_at"], utc=True).isna().any():
        raise ValueError("Universe has invalid available_at")
    return {"rows": len(frame), "codes": int(frame["code"].nunique()), "key_unique": True,
            "hash_unique": True, "available_at_timezone_aware": True,
            "status": "FORWARD_ONLY_CANDIDATE_NOT_HISTORICAL"}


def publish_universe_candidate(frame: pd.DataFrame, release_id: str, lake_root: Path) -> dict[str, Any]:
    checks = validate_universe(frame)
    target = Path(lake_root).resolve() / "v2" / "silver" / "universe_pit_v2" / "_releases" / release_id
    if target.exists(): raise ValueError("target exists: %s" % target)
    staging = target.parent / (".staging-" + release_id); staging.mkdir(parents=True, exist_ok=False)
    try:
        frame.to_parquet(staging / "universe_pit.parquet", index=False, engine="pyarrow", compression="zstd")
        manifest = {"schema_version": 2, "kind": "unified_v2_universe_pit_candidate", "release_id": release_id,
                    "status": "PUBLISHED_ISOLATED_UNIVERSE_PIT_CANDIDATE", "created_at": datetime.now(timezone.utc).isoformat(),
                    **checks, "target": str(target), "global_latest_updated": False, "legacy_data_modified": False,
                    "global_publishable": False, "limitations": ["membership starts only at explicit effective_from", "not a historical universe backfill"]}
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True); os.replace(staging, target); return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True); raise
