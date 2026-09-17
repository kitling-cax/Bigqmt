"""Promote a verified U25 research release without touching global PIT."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.research_catalog_v2 import promote_isolated_research_release  # noqa: E402
from kitling_bigqmt.unified_lake_v2 import contract_sha256, load_contract  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Atomically promote isolated U25 research PIT")
    parser.add_argument("release", type=Path)
    parser.add_argument("--catalog", type=Path,
                        default=Path(r"C:\BigQMT\research\quant_data_lake\v2\catalog\LATEST_RESEARCH.json"))
    parser.add_argument("--expected-previous-release", required=True)
    parser.add_argument("--approve-isolated-research-promotion", action="store_true")
    args = parser.parse_args()
    if not args.approve_isolated_research_promotion:
        raise SystemExit("refusing promotion without --approve-isolated-research-promotion")
    contract = load_contract(ROOT / "config" / "unified_data_lake_v2_contract.json")
    result = promote_isolated_research_release(
        args.catalog, "U25_ETF_RESEARCH_PIT", args.release,
        expected_previous_release=args.expected_previous_release,
        contract_sha256=contract_sha256(contract),
    )
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
