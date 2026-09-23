"""One bounded, read-only collection cycle from the QMT bridge."""

from __future__ import annotations

from typing import Any

from .readonly_rpc import ReadOnlyBigQmtClient


def collect_readonly_snapshot(client: ReadOnlyBigQmtClient, quote_codes: list[str] | None = None) -> dict[str, Any]:
    bundle = {
        "ping": client.ping(),
        "asset": client.account_asset(),
        "positions": client.positions(),
        "orders": client.orders(),
        "trades": client.trades(),
    }
    positions_data = bundle["positions"].get("data") or []
    if isinstance(positions_data, dict):
        # 0.3.26 bridge shape: dict keyed by stock_code
        dynamic_codes = list(positions_data.keys())
    elif isinstance(positions_data, list):
        # 0.3.54+ bridge shape: list of position dicts, each with stock_code
        dynamic_codes = [
            item["stock_code"]
            for item in positions_data
            if isinstance(item, dict) and item.get("stock_code")
        ]
    else:
        dynamic_codes = []
    codes = list(quote_codes or dynamic_codes)
    bundle["quotes"] = client.full_tick(codes) if codes else {"data": {}}
    return bundle
