"""Compare MiniQMT candidate bars with BigQMT and Tushare (read-only)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.lake_ingest_v2 import normalize_tushare  # noqa: E402


def _mini(paths: list[Path]) -> pd.DataFrame:
    d = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    return d[d["frequency"].astype(str) == "1d"].copy()


def _read_parquet_tree(path: Path) -> pd.DataFrame:
    files = sorted(path.rglob("*.parquet")) if path.is_dir() else [path]
    if not files:
        raise ValueError(f"no parquet files under {path}")
    return pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)


def _frequency_one_day(frame: pd.DataFrame) -> pd.DataFrame:
    col = "frequency" if "frequency" in frame.columns else "period"
    return frame[frame[col].astype(str).isin({"1d", "D", "day"})].copy()


def _field(frame: pd.DataFrame, *names: str) -> str:
    for name in names:
        if name in frame.columns:
            return name
    raise ValueError(f"none of fields exist: {names}")


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--miniqmt", type=Path, nargs="+", required=True); parser.add_argument("--bigqmt", type=Path, required=True); parser.add_argument("--tushare", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    m = _mini(args.miniqmt)
    m_duplicate_keys = int(m.duplicated(["code", "trade_date"]).sum())
    # Multiple probe files may intentionally overlap (e.g. U25 plus a unit
    # sample). Deduplicate only identical business keys for comparison and
    # retain the count in evidence; conflicting rows are reported below.
    m_conflicting_keys = int(m.groupby(["code", "trade_date"], dropna=False).size().gt(1).sum())
    m = m.drop_duplicates(["code", "trade_date"], keep="first")
    b = _frequency_one_day(_read_parquet_tree(args.bigqmt))
    t_raw = _read_parquet_tree(args.tushare)
    # Accept both the pre-ingest Tushare repair schema and the published
    # canonical Bronze schema.  This keeps reconciliation useful after a
    # candidate release is materialized, without changing any source values.
    if {"ts_code", "new_open", "new_close"}.issubset(t_raw.columns):
        t = normalize_tushare(t_raw, "tushare_repair_candidate", set())
    else:
        t = _frequency_one_day(t_raw)
    for d in (m, b, t): d["trade_date"] = d["trade_date"].astype(str); d["code"] = d.get("code", d.get("ts_code")).astype(str).str.upper()
    m = m.set_index(["code", "trade_date"]); b = b.set_index(["code", "trade_date"]); t = t.set_index(["code", "trade_date"])
    common_mb = sorted(set(m.index) & set(b.index)); common_mt = sorted(set(m.index) & set(t.index))
    def compare(keys, other, amount_col, volume_col):
        out = []
        for key in keys:
            x, y = m.loc[key], other.loc[key]
            diffs = {field: float(x[field]) - float(y[src]) for field, src in (("open", "open"), ("high", "high"), ("low", "low"), ("close", "close"), ("volume", volume_col), ("amount", amount_col))}
            out.append({"code": key[0], "trade_date": key[1], "diffs": diffs})
        return out
    b_amount = _field(b, "amount_yuan", "raw_amount", "amount")
    b_volume = _field(b, "volume_lots", "raw_volume", "volume")
    mb = compare(common_mb, b, b_amount, b_volume)
    # Tushare daily.amount is thousand CNY; compare on the canonical yuan
    # scale while retaining the source unit in its own normalized table.
    t = t.copy()
    if "raw_amount_unit" in t.columns:
        t["raw_amount_yuan"] = t["raw_amount"] * t["raw_amount_unit"].map(lambda u: 1000.0 if str(u) == "thousand_cny" else 1.0)
    else:
        t["raw_amount_yuan"] = t["raw_amount"] * 1000.0
    t_volume = _field(t, "raw_volume", "volume")
    mt = compare(common_mt, t, "raw_amount_yuan", t_volume)
    def within_gate(rows):
        return sum(
            all(abs(x["diffs"][k]) <= (1e-6 if k in {"open", "high", "low", "close"} else 1 if k == "volume" else 200) for k in x["diffs"])
            for x in rows
        )
    result = {"schema_version": 1, "kind": "miniqmt_source_reconciliation", "created_at": datetime.now(timezone.utc).isoformat(), "miniqmt_rows": int(len(m)), "miniqmt_duplicate_input_keys": m_duplicate_keys, "miniqmt_conflicting_input_keys": m_conflicting_keys, "bigqmt_rows": int(len(b)), "tushare_rows": int(len(t)), "common_miniqmt_bigqmt": len(common_mb), "common_miniqmt_tushare": len(common_mt), "within_tolerance": {"bigqmt": within_gate(mb), "tushare": within_gate(mt), "tolerance": {"price": 1e-6, "volume": 1, "amount_yuan": 200}}, "bigqmt_comparison": mb, "tushare_comparison": mt, "status": "CANDIDATE_RECONCILED_READ_ONLY", "lake_write": False, "global_latest_updated": False, "orders_enabled": False, "broker_calls": False}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"); print(json.dumps({k: result[k] for k in ("status", "miniqmt_rows", "common_miniqmt_bigqmt", "common_miniqmt_tushare", "lake_write", "global_latest_updated")}, ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
