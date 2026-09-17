"""Evidence-gated PIT builder for v2.

This builder supports the verified split-only path and deliberately refuses
cash/rights actions unless their numeric factor and available_at contracts are
explicitly verified.  It never infers factors from adjusted prices.
"""
from __future__ import annotations
from typing import Any
import pandas as pd


class PitBuilderV2Error(ValueError):
    pass


def build_split_only_pit(raw: pd.DataFrame, actions: pd.DataFrame, release_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_raw = {"code", "trade_date", "open", "high", "low", "close", "raw_volume", "raw_amount", "received_at"}
    required_actions = {"code", "ex_date", "qmt_bonus_ratio", "available_at", "numeric_status"}
    if missing := sorted(required_raw - set(raw.columns)):
        raise PitBuilderV2Error("raw missing: %s" % ",".join(missing))
    if missing := sorted(required_actions - set(actions.columns)):
        raise PitBuilderV2Error("actions missing: %s" % ",".join(missing))
    if actions.empty:
        raise PitBuilderV2Error("no verified actions")
    if (actions["numeric_status"] != "VERIFIED_SPLIT_RATIO").any():
        raise PitBuilderV2Error("split PIT requires VERIFIED_SPLIT_RATIO actions")
    if actions["available_at"].isna().any():
        raise PitBuilderV2Error("split PIT requires available_at")
    output = []
    by_event = {(str(row.code), str(row.ex_date)): row for row in actions.itertuples()}
    for code, group in raw.groupby("code", sort=True):
        factor = 1.0; factor_at = None
        for item in group.sort_values("trade_date").itertuples():
            event = by_event.get((str(code), str(item.trade_date)))
            if event:
                factor *= 1.0 + float(event.qmt_bonus_ratio); factor_at = str(event.available_at)
            bar_at = str(item.received_at)
            available = max(pd.Timestamp(bar_at), pd.Timestamp(factor_at or bar_at))
            row = {"code": str(code), "trade_date": str(item.trade_date), "open": float(item.open) * factor,
                   "high": float(item.high) * factor, "low": float(item.low) * factor, "close": float(item.close) * factor,
                   "open_raw": float(item.open), "high_raw": float(item.high), "low_raw": float(item.low), "close_raw": float(item.close),
                   "volume": float(item.raw_volume), "amount": float(item.raw_amount), "adjustment_factor": factor,
                   "adjustment_method": "SPLIT_ONLY_REBUILT_FROM_RAW", "bar_available_at": bar_at,
                   "factor_available_at": factor_at or bar_at, "available_at": available.isoformat(),
                   "source_version": release_id}
            output.append(row)
    frame = pd.DataFrame(output)
    if frame.empty or frame[["code", "trade_date"]].duplicated().any() or (frame["adjustment_factor"] <= 0).any():
        raise PitBuilderV2Error("PIT output key/factor validation failed")
    return frame, {"rows": len(frame), "codes": int(frame.code.nunique()), "adjustment_method": "SPLIT_ONLY_REBUILT_FROM_RAW", "pit_ready": True}
