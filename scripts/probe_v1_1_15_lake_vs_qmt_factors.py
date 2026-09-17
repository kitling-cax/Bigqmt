"""Compare local lake factors with QMT price modes for parity-difference cases.

The lake is not used to generate signals here.  This report only answers
whether the project's existing ETF lake reproduces QMT ``front/back/none``
values for the dates that still differ from PTrade.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import duckdb
except ImportError as exc:  # pragma: no cover - host diagnostic dependency
    raise SystemExit("duckdb is required for this diagnostic: %s" % exc)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.market_data import normalize_daily_bars  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.v1_1_15_reproduction import legacy_weighted_momentum, ptrade_to_qmt  # noqa: E402


DEFAULT_DIAGNOSIS = ROOT / "runtime_data" / "evidence" / "simulation" / (
    "qmt_v1_1_15_rank_difference_diagnosis_20260908_140836.json"
)
DEFAULT_LAKE = Path(r"C:\BigQMT\research\quant_data_lake\silver\bars_pit\year=*\*.parquet")


def qmt_score(client, qmt_code, day, adjustment):
    envelope = None
    last_error = None
    for _ in range(3):
        try:
            envelope = client.market_data_ex(
                [qmt_code], ["close", "time"], "1d", "20150101", day, -1, adjustment
            )
            break
        except TimeoutError as exc:
            last_error = exc
    if envelope is None:
        raise last_error
    bars = normalize_daily_bars(envelope, qmt_code)
    values = [float(bar.close) for bar in bars
              if bar.close is not None and bar.close > 0 and bar.trade_date <= day]
    return {
        "usable_bars": len(values),
        "last_close": values[-1] if values else None,
        "score": legacy_weighted_momentum(values[-25:]),
    }


def lake_scores(con, lake_glob, code, day):
    lake_code = code.replace(".SS", ".SH")
    date = "%s-%s-%s" % (day[:4], day[4:6], day[6:])
    rows = con.execute(
        "select close, adjustment_factor, source from read_parquet(?) "
        "where code=? and cast(trade_date as date)<=? and close>0 order by trade_date",
        [lake_glob, lake_code, date],
    ).fetchall()
    raw = [float(row[0]) for row in rows]
    adjusted = [float(row[0]) / float(row[1]) for row in rows
                if row[1] not in (None, 0)]
    return {
        "usable_bars": len(rows),
        "last_close": raw[-1] if raw else None,
        "raw_score": legacy_weighted_momentum(raw[-25:]),
        "factor_adjusted_score": legacy_weighted_momentum(adjusted[-25:]),
        "sources": sorted(set(row[2] for row in rows if row[2])),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnosis", type=Path, default=DEFAULT_DIAGNOSIS)
    parser.add_argument("--lake-glob", type=Path, default=DEFAULT_LAKE)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    diagnosis = json.loads(args.diagnosis.read_text(encoding="utf-8"))
    cases = []
    for item in diagnosis["differences"]:
        code = item["qmt_best"] if item["category"] == "DATA_OR_ELIGIBILITY_DIFFERENCE" else item["ptrade_best"]
        cases.append((code, item["day"], item["category"]))

    config = load_gateway(ROOT, "simulation") if args.config is None else json.loads(args.config.read_text(encoding="utf-8"))
    client = ReadOnlyBigQmtClient(
        RedisRespClient(**dict(config["redis"])), str(config["account_id"]),
        timeout_seconds=float(config.get("rpc_timeout_seconds", 12)),
    )
    con = duckdb.connect()
    rows = []
    for code, day, category in cases:
        qmt_code = ptrade_to_qmt(code)
        entry = {"code": code, "day": day, "category": category, "qmt_code": qmt_code}
        try:
            entry["qmt"] = {mode: qmt_score(client, qmt_code, day, mode)
                             for mode in ("front", "back", "none")}
            entry["lake"] = lake_scores(con, str(args.lake_glob), code, day)
            entry["qmt_front_matches_lake_raw"] = (
                entry["qmt"]["front"]["score"] is not None and
                entry["lake"]["raw_score"] is not None and
                abs(entry["qmt"]["front"]["score"] - entry["lake"]["raw_score"]) <= 0.00005
            )
        except Exception as exc:
            entry["error"] = {"type": type(exc).__name__, "message": str(exc)}
        rows.append(entry)

    matched = [row for row in rows if row.get("qmt_front_matches_lake_raw")]
    artifact = {
        "schema_version": 1,
        "kind": "qmt_v1_1_15_lake_vs_qmt_factor_probe",
        "created_at": datetime.now().astimezone().isoformat(),
        "orders_enabled": False,
        "diagnosis_file": str(args.diagnosis),
        "lake_glob": str(args.lake_glob),
        "case_count": len(rows),
        "qmt_front_matches_lake_raw_count": len(matched),
        "interpretation": "This is a read-only source comparison, not a PTrade parity pass and not a signal source switch.",
        "cases": rows,
    }
    output = args.output or (ROOT / "runtime_data" / "evidence" / "simulation" /
                             ("qmt_v1_1_15_lake_vs_qmt_factor_probe_%s.json" %
                              datetime.now().strftime("%Y%m%d_%H%M%S")))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output), "case_count": len(rows),
        "qmt_front_matches_lake_raw_count": len(matched), "orders_enabled": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
