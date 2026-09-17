"""Pure, side-effect-free reproduction core for PTrade v1.1.15.

The module intentionally contains no QMT or order calls.  It mirrors the
frozen PTrade scoring and close-signal decision rules so that QMT data can be
compared before an execution adapter is considered.  Prices supplied to this
module must already be separated into adjusted (signal) and raw (risk)
series; choosing a QMT adjustment mode is an evidence decision outside this
module.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, MutableMapping, Sequence


UNIVERSE_PTRADE = (
    "518880.SS", "501225.SS", "513030.SS", "563230.SS", "512980.SS",
    "513090.SS", "512200.SS", "162415.SZ", "159915.SZ", "159985.SZ",
    "161226.SZ", "159941.SZ", "161127.SZ", "159852.SZ", "162719.SZ",
    "159582.SZ", "162411.SZ", "159995.SZ", "160723.SZ", "159667.SZ",
    "159530.SZ", "159611.SZ", "159992.SZ", "515880.SS", "159755.SZ",
)
FALLBACK_PTRADE = "511880.SS"
MOMENTUM_WINDOW = 25
SMA_WINDOW = 4
MOMENTUM_MIN = 0.05
MOMENTUM_MAX = 2.00
SWITCH_IMPROVEMENT = 0.05
STOP_DAILY_DROP = -0.04
STOP_DRAWDOWN = -0.05
TAKE_PROFIT = 0.12
STOP_FREEZE_DAYS = 1
TAKE_PROFIT_FREEZE_DAYS = 2


def ptrade_to_qmt(code: str) -> str:
    if code.endswith(".SS"):
        return code[:-3] + ".SH"
    if code.endswith(".SZ"):
        return code
    raise ValueError("unsupported PTrade security suffix: %s" % code)


def legacy_weighted_momentum(closes: Sequence[float]) -> float | None:
    """Exact v1.1.15 weighted log-regression score, including truncation."""
    if len(closes) != MOMENTUM_WINDOW:
        return None
    logs: list[float] = []
    for close in closes:
        try:
            value = float(close)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value <= 0:
            return None
        logs.append(math.log(value))
    n = len(logs)
    sum_w = sum_wx = sum_wy = sum_wxx = sum_wxy = 0.0
    for index, y in enumerate(logs):
        linear_weight = 1.0 + float(index) / float(n - 1)
        regression_weight = linear_weight * linear_weight
        x = float(index)
        sum_w += regression_weight
        sum_wx += regression_weight * x
        sum_wy += regression_weight * y
        sum_wxx += regression_weight * x * x
        sum_wxy += regression_weight * x * y
    denominator = sum_w * sum_wxx - sum_wx * sum_wx
    if denominator == 0:
        return None
    slope = (sum_w * sum_wxy - sum_wx * sum_wy) / denominator
    intercept = (sum_wy - slope * sum_wx) / sum_w
    mean_y = sum(logs) / float(n)
    ss_res = ss_tot = 0.0
    for index, y in enumerate(logs):
        linear_weight = 1.0 + float(index) / float(n - 1)
        residual = y - (intercept + slope * float(index))
        ss_res += linear_weight * residual * residual
        centered = y - mean_y
        ss_tot += linear_weight * centered * centered
    if ss_tot <= 0:
        return None
    try:
        annual_return = math.exp(slope * 250.0) - 1.0
    except OverflowError:
        return None
    value = annual_return * (1.0 - ss_res / ss_tot)
    return int(value * 10000.0) / 10000.0


def score_market(market: Mapping[str, Mapping[str, Sequence[float]]]) -> dict[str, Any]:
    """Calculate scores and SMA4 eligibility exactly as the PTrade loop."""
    scores: dict[str, float] = {}
    sma_pass: dict[str, bool] = {}
    rejected: dict[str, str] = {}
    for code in UNIVERSE_PTRADE:
        item = market.get(code, {})
        adjusted = list(item.get("adjusted", ()))
        score = legacy_weighted_momentum(adjusted[-MOMENTUM_WINDOW:])
        if score is None:
            rejected[code] = "INSUFFICIENT_OR_INVALID_ADJUSTED_CLOSE"
            continue
        if score < MOMENTUM_MIN or score > MOMENTUM_MAX:
            rejected[code] = "SCORE_OUT_OF_RANGE"
            continue
        scores[code] = score
        if len(adjusted) >= SMA_WINDOW:
            sma = sum(adjusted[-SMA_WINDOW:]) / float(SMA_WINDOW)
            sma_pass[code] = adjusted[-1] > sma
    best = sorted(scores, key=lambda code: scores[code], reverse=True)[0] if scores else None
    return {"scores": scores, "sma_pass": sma_pass, "rejected": rejected, "best": best}


def new_state(name: str = "RC1") -> dict[str, Any]:
    return {
        "name": name, "current": None, "entry_price": 0.0, "entry_day": None,
        "hold_days": 0, "highest_raw_close": 0.0, "last_close": 0.0,
        "last_close_day": None, "frozen_sessions": {}, "pending_target": None,
        "pending_reason": None, "signal_day": None,
    }


def advance_freezes(state: MutableMapping[str, Any]) -> None:
    frozen = state.setdefault("frozen_sessions", {})
    for security in list(frozen):
        frozen[security] -= 1
        if frozen[security] <= 0:
            del frozen[security]


def _update_close_state(state: MutableMapping[str, Any], current: str,
                        item: Mapping[str, Sequence[float]], day: str) -> None:
    raw = list(item.get("raw", ())) if item else []
    if not raw:
        return
    close = float(raw[-1])
    if state.get("entry_day") is None:
        state["entry_day"] = day
        state["hold_days"] = 1
    elif state.get("last_close_day") != day:
        state["hold_days"] = int(state.get("hold_days", 0)) + 1
    state["last_close_day"] = day
    state["last_close"] = close
    state["highest_raw_close"] = max(float(state.get("highest_raw_close", 0.0)), close)


def _risk_reason(state: Mapping[str, Any], item: Mapping[str, Sequence[float]]) -> str | None:
    raw = list(item.get("raw", ())) if item else []
    if not raw:
        return None
    close = float(raw[-1])
    previous = float(raw[-2]) if len(raw) >= 2 else 0.0
    if previous > 0 and close / previous - 1.0 <= STOP_DAILY_DROP:
        return "DAILY_DROP"
    high = float(state.get("highest_raw_close", 0.0))
    if high > 0 and close / high - 1.0 <= STOP_DRAWDOWN:
        return "DRAWDOWN"
    entry = float(state.get("entry_price", 0.0))
    if entry > 0 and close / entry - 1.0 >= TAKE_PROFIT:
        return "TAKE_PROFIT"
    return None


def close_signal(state: MutableMapping[str, Any], market: Mapping[str, Mapping[str, Sequence[float]]],
                 day: str, min_hold_days: int = 5) -> dict[str, Any]:
    """Apply one PTrade-style after_trading_end signal step.

    The returned record is a signal intent.  It does not submit or simulate a
    fill; callers must explicitly call :func:`virtual_fill` when constructing
    a historical target sequence.
    """
    current = state.get("current")
    if current:
        _update_close_state(state, current, market.get(current, {}), day)
    scored = score_market(market)
    scores = scored["scores"]
    sma_pass = scored["sma_pass"]
    best = scored["best"]
    risk = _risk_reason(state, market.get(current, {})) if current else None
    if risk:
        cooldown = TAKE_PROFIT_FREEZE_DAYS if risk == "TAKE_PROFIT" else STOP_FREEZE_DAYS
        state.setdefault("frozen_sessions", {})[current] = cooldown + 1
        risk_scores = {code: score for code, score in scores.items() if code != current}
        risk_best = max(risk_scores, key=risk_scores.get) if risk_scores else None
        desired = risk_best or (FALLBACK_PTRADE if market.get(FALLBACK_PTRADE, {}).get("raw") else None)
        reason = "RISK_%s_DIRECT_RANK" % risk
    elif current and int(state.get("hold_days", 0)) < min_hold_days:
        desired, reason = current, "MIN_HOLD_%d" % min_hold_days
    elif current is None:
        if best and sma_pass.get(best):
            desired, reason = best, "EMPTY_TO_BEST_SMA4"
        else:
            desired, reason = FALLBACK_PTRADE, "EMPTY_TO_FALLBACK"
    else:
        current_score = scores.get(current)
        if current_score is None:
            if best and sma_pass.get(best):
                desired, reason = best, "CURRENT_SCORE_INVALID_BEST_SMA4"
            else:
                desired, reason = current, "CURRENT_SCORE_INVALID_HOLD"
        elif best and best != current and sma_pass.get(best) and scores[best] > current_score * 1.05:
            desired, reason = best, "BETTER_BY_5PCT_SMA4"
        else:
            desired, reason = current, "NO_SWITCH"
    if state.get("pending_target"):
        desired, reason = state["pending_target"], "PENDING_TARGET"
    changed = desired != current
    if changed and not state.get("pending_target"):
        state["pending_target"] = desired
        state["pending_reason"] = reason
        state["signal_day"] = day
    return {
        "day": day, "current": current, "desired": desired, "changed": changed,
        "reason": reason, "best": best, "risk": risk,
        "scores": dict(scores), "sma_pass": dict(sma_pass),
    }


def virtual_fill(state: MutableMapping[str, Any], day: str, price: float) -> dict[str, Any] | None:
    """Explicitly transition a pending target at a supplied next-session price."""
    target = state.get("pending_target")
    if not target:
        return None
    old = state.get("current")
    state["current"] = target
    state["entry_price"] = float(price)
    state["entry_day"] = day
    state["hold_days"] = 0
    state["highest_raw_close"] = float(price)
    state["last_close"] = float(price)
    state["last_close_day"] = None
    state["pending_target"] = None
    state["pending_reason"] = None
    state["signal_day"] = None
    return {"day": day, "from": old, "to": target, "price": float(price)}
