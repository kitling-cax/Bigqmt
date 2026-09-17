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
    dynamic_codes = list((bundle["positions"].get("data") or {}).keys())
    codes = list(quote_codes or dynamic_codes)
    bundle["quotes"] = client.full_tick(codes) if codes else {"data": {}}
    return bundle
