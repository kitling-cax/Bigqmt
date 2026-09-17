"""Convert reconciled QMT corporate-action evidence into an isolated Bronze candidate."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def build_action_rows(evidence: dict[str, Any], etf_codes: set[str], release_id: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for event in evidence.get("events", []):
        code = str(event.get("code") or "").upper()
        payload = list(event.get("qmt_payload") or [])
        if not code or not event.get("qmt_event_date"):
            continue
        cash = float(payload[0]) if len(payload) > 0 and payload[0] is not None else 0.0
        bonus = float(payload[1]) if len(payload) > 1 and payload[1] is not None else 0.0
        transfer = float(payload[2]) if len(payload) > 2 and payload[2] is not None else 0.0
        rights_ratio = float(payload[3]) if len(payload) > 3 and payload[3] is not None else 0.0
        rights_price = float(payload[4]) if len(payload) > 4 and payload[4] is not None else 0.0
        action_type = "cash_dividend" if cash else ("share_split_or_bonus" if bonus or transfer else ("rights_issue" if rights_ratio else "other"))
        ts_rows = event.get("tushare_action_rows") or []
        ext = ts_rows[0] if ts_rows else {}
        announcements = event.get("announcement_candidates") or []
        row: dict[str, Any] = {
            "code": code, "asset_class": "etf" if code in etf_codes else "stock", "action_type": action_type,
            "ex_date": str(event["qmt_event_date"]), "announcement_at": None, "available_at": None,
            "available_at_policy": "DATE_ONLY_REVIEW_ONLY",
            "qmt_cash_per_share": cash, "qmt_bonus_ratio": bonus, "qmt_transfer_ratio": transfer,
            "qmt_rights_ratio": rights_ratio, "qmt_rights_price": rights_price,
            "qmt_cumulative_factor": float(payload[6]) if len(payload) > 6 and payload[6] is not None else None,
            "external_cash_per_share": float(ext["cash_div"]) if ext.get("cash_div") not in (None, "") else None,
            "external_bonus_ratio": float(ext["stk_div"]) if ext.get("stk_div") not in (None, "") else None,
            "announcement_date_candidates": json.dumps([str(item.get("announcement_date")) for item in announcements], ensure_ascii=False),
            "source": "qmt_divid_factors_reconciled_with_tushare_akshare",
            "source_endpoint": "QMT:get_divid_factors;Tushare:dividend;AkShare:fund_cf_em",
            "unit_contract_version": "bigqmt_pit_unit_contract_draft_v1",
            "numeric_status": str(event.get("numeric_factor_status") or "UNVERIFIED"),
            "date_status": "VERIFIED_EVENT_DATE" if event.get("event_date_match") else "UNVERIFIED_EVENT_DATE",
            "release_id": release_id,
        }
        row["row_hash"] = _hash(row)
        output.append(row)
    return output


def publish_action_candidate(rows: list[dict[str, Any]], release_id: str, lake_root: Path) -> dict[str, Any]:
    if not rows:
        raise ValueError("no corporate-action rows")
    frame = pd.DataFrame(rows)
    target = Path(lake_root).resolve() / "v2" / "bronze" / "corporate_actions" / "_releases" / release_id
    if target.exists():
        raise ValueError("target exists: %s" % target)
    staging = target.parent / (".staging-" + release_id)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        frame["year"] = frame["ex_date"].str[:4].astype(int)
        for year, group in frame.groupby("year", sort=True):
            path = staging / ("year=%s" % year); path.mkdir(parents=True, exist_ok=True)
            group.drop(columns=["year"]).to_parquet(path / "part-0.parquet", index=False, engine="pyarrow", compression="zstd")
        date_verified = int((frame["date_status"] == "VERIFIED_EVENT_DATE").sum())
        manifest = {"schema_version": 2, "kind": "unified_v2_corporate_actions_candidate", "release_id": release_id,
                    "status": "PUBLISHED_ISOLATED_CORPORATE_ACTION_CANDIDATE", "created_at": datetime.now(timezone.utc).isoformat(),
                    "rows": len(frame), "codes": int(frame["code"].nunique()), "event_dates_verified": date_verified,
                    "numeric_factor_gate": "BLOCKED_UNVERIFIED", "available_at_gate": "BLOCKED_DATE_ONLY",
                    "target": str(target), "global_latest_updated": False, "legacy_data_modified": False,
                    "silver_pit_ready": False, "orders_enabled": False,
                    "limitations": ["QMT cumulative factor is diagnostic only", "announcement timestamps absent", "unit contract remains draft"]}
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True); os.replace(staging, target)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True); raise
