"""Read-only PIT/adjustment-factor coverage gate for BigQMT candidates."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
LAKE_ROOT = Path(r"C:/BigQMT/research/quant_data_lake")
EVIDENCE_DIR = ROOT / "runtime_data" / "evidence" / "simulation" / "bigqmt_missing_key_scans"


def _latest_validation() -> Path:
    paths = sorted(EVIDENCE_DIR.glob("validated_missing_daily_*.json"), reverse=True)
    if not paths:
        raise FileNotFoundError("no validated_missing_daily evidence found")
    return paths[0]


def run(validation_path: Path) -> dict:
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    missing = validation.get("missing_candidate_keys") or []
    keys = {
        (str(item["code"]), str(item["trade_date"]), str(item.get("period", "1d")), str(item.get("adjustment_mode", "none")))
        for item in missing
    }
    evidence_path = EVIDENCE_DIR / f"pit_factor_coverage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result: dict = {
        "schema_version": 1,
        "kind": "bigqmt_candidate_pit_factor_coverage",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "mode": "READ_ONLY_NO_IMPORT",
        "input_validation_evidence": str(validation_path),
        "lake_root": str(LAKE_ROOT),
        "source_table": "silver/bars_pit/year=YYYY",
        "business_key": ["code", "trade_date", "period=1d", "adjustment_mode=none"],
        "candidate_keys": len(keys),
        "pit_rows_for_candidate_keys": 0,
        "factor_nonnull_rows": 0,
        "covered_candidate_keys": 0,
        "missing_factor_keys": [],
        "status": "BLOCKED",
        "overlay_created": False,
        "global_latest_updated": False,
    }
    if not keys:
        result["status"] = "BLOCKED_NO_CANDIDATES"
        evidence_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    codes = sorted({key[0] for key in keys})
    dates = sorted({key[1] for key in keys})
    min_date = f"{min(dates)[:4]}-{min(dates)[4:6]}-{min(dates)[6:]}"
    max_date = f"{max(dates)[:4]}-{max(dates)[4:6]}-{max(dates)[6:]}"
    pit_glob = str(LAKE_ROOT / "silver" / "bars_pit" / "year=*" / "*.parquet")
    con = duckdb.connect()
    try:
        frame = con.execute(
            """
            select code, cast(trade_date as date) as trade_date, adjustment_factor
            from read_parquet(?, union_by_name=true, hive_partitioning=true)
            where code in (select unnest(?::varchar[]))
              and cast(trade_date as date) between ?::date and ?::date
            """,
            [pit_glob, codes, min_date, max_date],
        ).fetchall()
    finally:
        con.close()

    covered = set()
    factor_rows = 0
    for code, trade_date, factor in frame:
        key = (str(code), trade_date.strftime("%Y%m%d"), "1d", "none")
        if key in keys:
            covered.add(key)
            if factor is not None:
                factor_rows += 1
    missing_factor = sorted(keys - covered)
    result.update(
        {
            "pit_rows_for_candidate_keys": len(covered),
            "factor_nonnull_rows": factor_rows,
            "covered_candidate_keys": len(covered),
            "missing_factor_keys": [
                {"code": code, "trade_date": date, "period": period, "adjustment_mode": mode}
                for code, date, period, mode in missing_factor
            ],
            "status": "PASSED" if not missing_factor and factor_rows == len(keys) else "BLOCKED",
            "next_gate": "canonical PIT factor chain may be joined" if not missing_factor else "obtain raw PIT/corporate-action evidence before overlay publication",
        }
    )
    evidence_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["evidence"] = str(evidence_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-evidence", type=Path, default=None)
    args = parser.parse_args()
    result = run(args.validation_evidence or _latest_validation())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
