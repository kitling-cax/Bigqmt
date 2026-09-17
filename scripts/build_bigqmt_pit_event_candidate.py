"""Build a local-only PIT event candidate from reconciliation evidence.

This is not a Silver table and deliberately carries date-only availability and
unverified numeric-factor status. It is safe to review, diff, and delete.
"""
from __future__ import annotations

import argparse, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/pit_event_reconciliation_20260912.json"

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--reconciliation", type=Path, default=DEFAULT); ap.add_argument("--output-dir", type=Path)
    a = ap.parse_args(); rec = json.loads(a.reconciliation.read_text(encoding="utf-8"))
    out = a.output_dir or (ROOT / "runtime_data/candidates" / f"bigqmt_pit_event_candidate_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for e in rec.get("events", []):
        rows.append({
            "code": e.get("code"), "event_date": e.get("qmt_event_date"),
            "qmt_payload_json": json.dumps(e.get("qmt_payload"), ensure_ascii=False, separators=(",", ":")),
            "event_date_match": bool(e.get("event_date_match")),
            "available_at_status": e.get("available_at_status"),
            "numeric_factor_status": e.get("numeric_factor_status"),
            "tushare_action_rows_json": json.dumps(e.get("tushare_action_rows", []), ensure_ascii=False, separators=(",", ":")),
            "candidate_status": "REVIEW_ONLY_DATE_MATCHED" if e.get("event_date_match") else "QUARANTINED_DATE_MISMATCH",
        })
    manifest = {
        "schema_version": 1, "kind": "bigqmt_pit_event_candidate", "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "LOCAL_REVIEW_ONLY_NO_SILVER_PUBLISH_NO_LAKE_WRITE", "source_reconciliation": str(a.reconciliation.resolve()),
        "row_count": len(rows), "event_date_matched": sum(1 for r in rows if r["event_date_match"]),
        "gates": {"event_date_reconciliation": rec.get("gates", {}).get("event_date_reconciliation"), "available_at": "BLOCKED_DATE_ONLY", "numeric_factor": "BLOCKED_UNVERIFIED", "silver_publish": "BLOCKED"},
        "safety": {"lake_write": False, "global_latest_updated": False, "orders_enabled": False},
        "files": ["pit_event_candidate.jsonl", "manifest.json"],
    }
    (out / "pit_event_candidate.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(out), "row_count": len(rows), "gates": manifest["gates"], "safety": manifest["safety"]}, ensure_ascii=False, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
