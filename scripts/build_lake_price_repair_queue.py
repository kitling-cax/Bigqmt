"""Materialize a local, read-only queue for existing lake price conflicts.

The queue is evidence for a future copy-on-write repair release.  It never
updates existing Parquet, DuckDB, catalog/LATEST, Redis, QMT, or broker state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _fingerprint(row: dict[str, Any]) -> str:
    text = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local lake price repair queue without modifying the lake")
    parser.add_argument(
        "evidence",
        nargs="?",
        type=Path,
        default=ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/lake_price_schema_conflicts_20260912_143912.json",
    )
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    rows = evidence.get("rows", [])
    front = evidence.get("front_reclassification_candidates", [])
    unmatched = evidence.get("unmatched_quarantine_candidates", [])
    errors: list[str] = []
    expected = evidence.get("summary", {}).get("classification_counts", {})
    actual = {}
    for row in rows:
        actual[str(row.get("classification"))] = actual.get(str(row.get("classification")), 0) + 1
    for name, count in expected.items():
        if int(actual.get(name, 0)) != int(count):
            errors.append(f"classification count mismatch for {name}: expected {count}, got {actual.get(name, 0)}")

    def _keys(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
        return [(str(item.get("code")), str(item.get("trade_date"))) for item in items]

    front_keys = _keys(front)
    unmatched_keys = _keys(unmatched)
    if len(set(front_keys)) != len(front_keys):
        errors.append("duplicate front reclassification business keys")
    if len(set(unmatched_keys)) != len(unmatched_keys):
        errors.append("duplicate unmatched quarantine business keys")
    if set(front_keys) & set(unmatched_keys):
        errors.append("front and unmatched repair queues overlap")

    queue = {
        "schema_version": 1,
        "kind": "lake_price_schema_repair_queue",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "LOCAL_EVIDENCE_ONLY_NO_LAKE_WRITE",
        "source_evidence": str(args.evidence.resolve()),
        "summary": {
            "lake_rows_checked": int(evidence.get("summary", {}).get("lake_rows_checked", 0)),
            "front_reclassification_candidates": len(front),
            "unmatched_quarantine_candidates": len(unmatched),
            "multiple_mode_rows": int(actual.get("MATCH_MULTIPLE_MODES", 0)),
            "matched_none_rows": int(actual.get("MATCH_QMT_NONE", 0)),
        },
        "queues": {
            "front_reclassification": {
                "status": "CANDIDATE_COPY_ON_WRITE_ONLY",
                "rule": "QMT front OHLC matches existing row; preserve old row and create a new versioned adjusted-layer candidate after review",
                "rows": [{**item, "queue_fingerprint": _fingerprint(item)} for item in front],
            },
            "unmatched_quarantine": {
                "status": "QUARANTINED",
                "rule": "price conflict remains unresolved; require independent source and unit review; never overwrite",
                "rows": [{**item, "queue_fingerprint": _fingerprint(item)} for item in unmatched],
            },
            "multiple_mode_provenance": {
                "status": "NO_AUTOMATIC_REPAIR",
                "rows": int(actual.get("MATCH_MULTIPLE_MODES", 0)),
                "rule": "values match more than one QMT mode; retain provenance ambiguity until a canonical price-mode decision",
            },
        },
        "gates": {
            "evidence_integrity": "PASSED" if not errors else "BLOCKED",
            "automatic_overwrite": "BLOCKED",
            "copy_on_write_release": "PENDING_REVIEW",
            "lake_write": False,
            "global_latest_updated": False,
        },
        "errors": errors,
        "next_action": "Review queue, obtain independent source for unmatched rows, then create a versioned repair release; never mutate existing bars_raw in place.",
    }
    out = ROOT / "runtime_data" / "evidence" / "simulation" / "bigqmt_missing_key_scans" / "lake_price_repair_queue_20260912.json"
    out.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), "summary": queue["summary"], "gates": queue["gates"]}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
