"""Collect bounded, read-only QMT quote-health evidence for selected symbols."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.quote_diagnostics import inspect_response
from kitling_bigqmt.redis_resp import RedisRespClient
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient
from kitling_bigqmt.machine_config import load_gateway

DEFAULT_CODES = ["511010.SH", "511990.SH", "513100.SH", "513500.SH", "518880.SH"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded read-only QMT quote diagnostic.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--codes", nargs="+", default=DEFAULT_CODES)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--max-age-seconds", type=float, default=180.0)
    parser.add_argument("--output", default="")
    arguments = parser.parse_args()
    if arguments.samples < 1 or arguments.interval_seconds <= 0 or arguments.max_age_seconds <= 0:
        raise ValueError("samples, interval-seconds and max-age-seconds must be positive")
    config = load_gateway(ROOT, "simulation") if arguments.config is None else json.loads(Path(arguments.config).read_text(encoding="utf-8"))
    client = ReadOnlyBigQmtClient(
        RedisRespClient(**dict(config["redis"])), str(config["account_id"]),
        float(config.get("rpc_timeout_seconds", 12)),
    )
    samples = []
    target = Path(arguments.output) if arguments.output else None
    for index in range(arguments.samples):
        try:
            samples.append(inspect_response(
                client.full_tick(list(arguments.codes)), list(arguments.codes), arguments.max_age_seconds,
            ))
        except Exception as error:
            # A timeout or transport failure is itself P04 evidence.  Preserve
            # it and continue sampling; never discard prior successful samples
            # or turn a gap into a synthetic price.
            samples.append({
                "schema_version": 1,
                "source": "simulation_bigqmt_redis_rpc",
                "sample_number": index + 1,
                "status": "ATTENTION",
                "error_type": type(error).__name__,
                "error": str(error),
                "orders_enabled": False,
            })
        report = {
            "schema_version": 1,
            "environment": config["environment"],
            "test": "qmt_quote_health_readonly",
            "requested_samples": arguments.samples,
            "completed_samples": len(samples),
            "samples": samples,
            "status": "PASSED" if len(samples) == arguments.samples and all(
                sample["status"] == "PASSED" for sample in samples
            ) else "ATTENTION",
            "orders_enabled": False,
        }
        # Persist after every sample so an interrupted process leaves useful,
        # append-safe evidence rather than losing the entire observation run.
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if index + 1 < arguments.samples:
            time.sleep(arguments.interval_seconds)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
