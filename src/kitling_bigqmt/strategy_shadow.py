"""Pure v1.1.15 close-shadow state transitions.

This module deliberately has no Redis, QMT, order, or accounting calls.  It
turns one completed daily-bar market snapshot into a durable *shadow* signal.
The virtual transition is only used to continue the signal state on the next
completed day; it is never a broker fill or a sleeve-accounting event.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from .state_store import as_json, sha256_hex
from .v1_1_15_reproduction import advance_freezes, close_signal, ptrade_to_qmt, virtual_fill


class ShadowStateError(ValueError):
    """Raised when a shadow transition cannot be made safely."""


def build_close_shadow_event(
    strategy_id: str,
    signal_day: str,
    market: Mapping[str, Mapping[str, list[float]]],
    prior_state: Mapping[str, Any] | None = None,
    prior_signal_day: str | None = None,
    adjustment_mode: str = "front",
    source_baseline_sha256: str = "",
) -> dict[str, Any]:
    """Produce one deterministic close-shadow event from completed bars.

    ``prior_state`` must be the state recorded for an earlier trading day.  A
    pending target is advanced using the current day's raw close strictly as a
    state-continuation approximation.  The returned event labels that fact so
    it cannot be mistaken for an order, fill, or performance record.
    """
    if not strategy_id or not signal_day:
        raise ShadowStateError("strategy_id and signal_day are required")
    if prior_signal_day and signal_day <= prior_signal_day:
        raise ShadowStateError("signal_day must be after prior_signal_day")

    state = copy.deepcopy(dict(prior_state or {}))
    if not state:
        from .v1_1_15_reproduction import new_state

        state = new_state("RC1_QMT_CLOSE_SHADOW")
    state_before = copy.deepcopy(state)
    virtual_transition = None
    pending_target = state.get("pending_target")
    if pending_target:
        raw = list((market.get(str(pending_target)) or {}).get("raw") or ())
        if not raw:
            raise ShadowStateError("pending target has no completed raw close")
        try:
            virtual_price = float(raw[-1])
        except (TypeError, ValueError):
            raise ShadowStateError("pending target raw close is invalid")
        if virtual_price <= 0:
            raise ShadowStateError("pending target raw close is not positive")
        virtual_transition = virtual_fill(state, signal_day, virtual_price)
        if virtual_transition is None:
            raise ShadowStateError("pending target could not advance")

    advance_freezes(state)
    decision = close_signal(state, market, signal_day, min_hold_days=5)
    desired_ptrade = decision.get("desired")
    desired_qmt = ptrade_to_qmt(str(desired_ptrade)) if desired_ptrade else None
    top_scores = sorted((decision.get("scores") or {}).items(), key=lambda item: item[1], reverse=True)[:5]
    identity = {
        "strategy_id": strategy_id,
        "signal_day": signal_day,
        "desired_ptrade": desired_ptrade,
        "reason": decision.get("reason"),
        "baseline": source_baseline_sha256,
        "adjustment_mode": adjustment_mode,
    }
    event_id = sha256_hex(as_json(identity))
    return {
        "schema_version": 1,
        "kind": "v1_1_15_qmt_close_shadow",
        "event_id": event_id,
        "strategy_id": strategy_id,
        "signal_day": signal_day,
        "adjustment_mode": adjustment_mode,
        "adjustment_parity": "UNVERIFIED_AGAINST_PTRade_DYPRE",
        "source_baseline_sha256": source_baseline_sha256,
        "orders_enabled": False,
        "broker_call_made": False,
        "execution_intent": "NONE_CLOSE_SIGNAL_ONLY",
        "virtual_transition": virtual_transition,
        "virtual_transition_disclaimer": (
            "raw-close state continuation only; not a broker order, broker fill, "
            "sleeve fill, valuation, or performance result"
        ),
        "state_before": state_before,
        "state_after": copy.deepcopy(state),
        "signal": {
            "current_ptrade": decision.get("current"),
            "current_qmt": ptrade_to_qmt(str(decision["current"])) if decision.get("current") else None,
            "desired_ptrade": desired_ptrade,
            "desired_qmt": desired_qmt,
            "changed": bool(decision.get("changed")),
            "reason": decision.get("reason"),
            "risk": decision.get("risk"),
            "best_ptrade": decision.get("best"),
            "best_qmt": ptrade_to_qmt(str(decision["best"])) if decision.get("best") else None,
            "top_scores": [{"security_ptrade": code, "security_qmt": ptrade_to_qmt(code), "score": score}
                           for code, score in top_scores],
        },
    }
