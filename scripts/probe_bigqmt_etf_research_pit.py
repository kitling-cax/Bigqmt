"""Read-only research probe for an isolated BigQMT ETF PIT release.

It emits trailing return and maximum-drawdown inputs for factor/backtest code;
it does not create a trading signal, recommendation, order, or catalog write.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.etf_research_pit import (  # noqa: E402
    filter_available_asof,
    load_research_release,
    trailing_return_drawdown_inputs,
)
DEFAULT_RELEASE = Path(r"C:\BigQMT\research\quant_data_lake\silver\_bigqmt_research_pit_releases\bigqmt_etf_research_pit_20260912_175315")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe backtest/factor inputs from isolated ETF research PIT")
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--asof", default="2026-09-11T15:30:00+08:00")
    parser.add_argument("--lookback", type=int, default=25)
    args = parser.parse_args()
    release = args.release.resolve()
    manifest, frame = load_research_release(release)
    usable = filter_available_asof(frame, args.asof)
    metrics = trailing_return_drawdown_inputs(usable, args.lookback)
    report = {
        "schema_version": 1, "kind": "bigqmt_etf_research_pit_probe",
        "created_at": datetime.now(timezone.utc).isoformat(), "release_id": manifest.get("release_id"),
        "asof": args.asof, "lookback_sessions": args.lookback,
        "rows_visible_asof": len(usable), "codes_visible_asof": int(usable["code"].nunique()),
        "metrics": metrics,
        "safety": {"read_only": True, "global_latest_updated": False, "broker_call": False, "orders_enabled": False},
        "limitations": ["metrics are research inputs, not a recommendation or execution signal",
                        "use only rows whose available_at is no later than the research as-of timestamp"],
    }
    directory = ROOT / "runtime_data" / "evidence" / "simulation" / "research_pit_probes"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / ("etf_research_pit_probe_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASSED", "evidence": str(output), "release_id": manifest.get("release_id"),
                      "rows_visible_asof": len(usable), "codes_visible_asof": int(usable["code"].nunique()),
                      "metric_rows": len(metrics), "safety": report["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
