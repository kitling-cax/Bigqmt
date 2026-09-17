"""Copy-on-write publish a conservative U25 ETF research PIT release.

The target is an isolated silver release.  This script never writes the
legacy ``silver/bars_pit`` dataset or ``catalog/LATEST.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
APPROVAL_TOKEN = "PUBLISH_BIGQMT_ETF_RESEARCH_PIT"
REQUIRED = {"code", "trade_date", "open", "high", "low", "close", "volume", "amount",
            "adjustment_factor", "bar_available_at", "factor_available_at", "available_at",
            "source", "source_release", "research_status", "row_hash"}


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def validate(candidate: Path) -> tuple[dict, pd.DataFrame]:
    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
    frame = pd.read_parquet(candidate / "etf_research_pit.parquet")
    missing = sorted(REQUIRED - set(frame.columns))
    if missing:
        raise ValueError("missing required columns: %s" % ",".join(missing))
    if manifest.get("mode") != "LOCAL_CANDIDATE_ONLY_NO_LAKE_WRITE":
        raise ValueError("candidate is not local-only")
    if (manifest.get("gates") or {}).get("research_backtest") != "PASSED":
        raise ValueError("research backtest gate not passed")
    if frame.empty or frame[["code", "trade_date"]].duplicated().any() or frame["row_hash"].duplicated().any():
        raise ValueError("empty or duplicate research candidate")
    for name in ("open", "high", "low", "close", "adjustment_factor"):
        if frame[name].isna().any() or (frame[name].astype(float) <= 0).any():
            raise ValueError("invalid %s" % name)
    if (frame["high"].astype(float) < frame[["open", "low", "close"]].astype(float).max(axis=1)).any():
        raise ValueError("high OHLC relation failed")
    if (frame["low"].astype(float) > frame[["open", "high", "close"]].astype(float).min(axis=1)).any():
        raise ValueError("low OHLC relation failed")
    if not (frame["available_at"] >= frame["bar_available_at"]).all():
        raise ValueError("available_at precedes bar availability")
    return manifest, frame


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish isolated BigQMT ETF research PIT")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    parser.add_argument("--approve-research-pit-publish", action="store_true")
    args = parser.parse_args()
    manifest, frame = validate(args.candidate.resolve())
    if not args.approve_research_pit_publish:
        print(json.dumps({"status": "READY_FOR_EXPLICIT_RESEARCH_PIT_PUBLISH", "release_id": manifest["release_id"],
                          "rows": len(frame), "lake_write": False, "global_latest_updated": False}, ensure_ascii=False, indent=2))
        return 0
    release_id = str(manifest["release_id"])
    lake = args.lake_root.resolve()
    target = lake / "silver" / "_bigqmt_research_pit_releases" / release_id
    if target.exists():
        existing = target / "publish_manifest.json"
        if existing.is_file():
            print(json.dumps({"status": "DUPLICATE", "target": str(target),
                              "manifest": json.loads(existing.read_text(encoding="utf-8"))}, ensure_ascii=False, indent=2))
            return 0
        raise ValueError("target exists without publish manifest")
    staging = lake / "_staging" / ("bigqmt_etf_research_pit_" + release_id)
    if staging.exists():
        raise ValueError("staging exists; inspect before retry")
    try:
        frame = frame.copy()
        frame["year"] = pd.to_datetime(frame["trade_date"]).dt.year.astype("int16")
        for year, group in frame.groupby("year", sort=True):
            directory = staging / "daily" / ("year=%s" % year)
            directory.mkdir(parents=True, exist_ok=True)
            group.to_parquet(directory / "part-0.parquet", index=False, engine="pyarrow", compression="zstd")
        shutil.copy2(args.candidate / "split_events.json", staging / "split_events.json")
        result = {
            "schema_version": 1, "release_id": release_id, "status": "PUBLISHED_ISOLATED_RESEARCH_PIT",
            "created_at": datetime.now(timezone.utc).isoformat(), "candidate": str(args.candidate.resolve()),
            "target": str(target), "rows": len(frame), "codes": int(frame["code"].nunique()),
            "events": int((manifest.get("events") or 0)), "research_backtest": "PASSED",
            "global_latest_updated": False, "legacy_silver_bars_pit_modified": False,
            "orders_enabled": False, "pit_scope": "ETF split-only conservative available_at policy",
            "tree_hash": tree_hash(staging), "approval_token_used": APPROVAL_TOKEN,
        }
        (staging / "publish_manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, target)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
