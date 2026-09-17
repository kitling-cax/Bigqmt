"""v1.1.17 ETF-pool benchmark helpers.

The benchmark is a synthetic, equal-weight daily-return chain.  It is only a
comparison series; it never represents broker holdings or an order target.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .market_data import normalize_daily_bars


BENCHMARK_CODE = "V1.1.17_ETF_POOL"
DEFAULT_POOL = (
    "518880.SH", "501225.SH", "513030.SH", "563230.SH", "512980.SH",
    "513090.SH", "512200.SH", "162415.SZ", "159915.SZ", "159985.SZ",
    "161226.SZ", "159941.SZ", "161127.SZ", "159852.SZ", "162719.SZ",
    "159582.SZ", "162411.SZ", "159995.SZ", "160723.SZ", "159667.SZ",
    "159530.SZ", "159611.SZ", "159992.SZ", "515880.SH", "159755.SZ",
)
DISPLAY_NAME = "v1.1.17 U25 无酒 ETF 池（等权）"


def load_pool(root: Path) -> tuple[str, ...]:
    """Load the frozen pool manifest, with a code fallback for portability."""

    path = root / "config" / "v1_1_17_etf_pool.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        codes = tuple(str(code).upper() for code in payload.get("qmt_codes", ()))
        if codes:
            return codes
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return DEFAULT_POOL


def _close_rows(client: Any, code: str, day: str) -> dict[str, float]:
    response = client.market_data_ex([code], ["close", "time"], "1d", "", day, -1, "none", subscribe=False)
    bars = normalize_daily_bars(response, code)
    return {bar.trade_date: float(bar.close) for bar in bars if bar.close and bar.close > 0 and bar.trade_date <= day}


def equal_weight_chain_point(client: Any, codes: tuple[str, ...], day: str,
                             previous_price: float | None = None) -> dict[str, Any]:
    """Return one pool index point, blocking on missing constituents.

    The first observation is rebased to 100.  Later observations compound the
    equal-weight mean of each constituent's latest daily return.
    """

    current: dict[str, float] = {}
    previous: dict[str, float] = {}
    missing: list[str] = []
    for code in codes:
        try:
            rows = _close_rows(client, code, day)
        except Exception:
            rows = {}
        dates = sorted(rows)
        if not dates or dates[-1] != day:
            missing.append(code)
            continue
        current[code] = rows[day]
        if len(dates) >= 2:
            previous[code] = rows[dates[-2]]
    if missing:
        raise ValueError("v1.1.17 ETF pool cache incomplete for %s: %s" % (day, ", ".join(missing)))
    if previous_price is None:
        index_price = 100.0
        mean_return = None
    else:
        if len(previous) != len(codes):
            raise ValueError("v1.1.17 ETF pool has no prior close for all constituents on %s" % day)
        returns = [(current[code] / previous[code]) - 1.0 for code in codes]
        mean_return = sum(returns) / len(returns)
        index_price = float(previous_price) * (1.0 + mean_return)
    return {
        "benchmark_code": BENCHMARK_CODE,
        "benchmark_name": DISPLAY_NAME,
        "price": index_price,
        "mean_return": mean_return,
        "constituent_count": len(codes),
        "constituents": list(codes),
    }
