import pytest

from kitling_bigqmt.simulation_execution import (
    SimulationExecutionBlocked,
    build_order_plan,
)


def _event(desired="160723.SZ", day="20260911"):
    return {"signal_day": day, "signal": {"desired_qmt": desired, "reason": "SMA4"}}


def _tick(code="160723.SZ", price=1.0):
    return {code: {"askPrice": [price], "bidPrice": [price], "lastPrice": price}}


def test_first_live_sleeve_buy_respects_98_percent_cap_and_lot():
    plan = build_order_plan(
        signal_event=_event(), activation_signal_not_before="20260911", trade_day="20260914",
        sleeve_summary={"cash": 100000, "positions": []}, ticks=_tick(),
    )
    assert plan["side"] == "BUY"
    assert plan["quantity"] % 100 == 0
    assert plan["quantity"] * plan["limit_price"] + plan["estimated_fee"] <= 100000


def test_existing_sleeve_position_sells_before_switching_to_a_new_target():
    plan = build_order_plan(
        signal_event=_event("518880.SH"), activation_signal_not_before="20260911", trade_day="20260914",
        sleeve_summary={"cash": 1000, "positions": [{"stock_code": "160723.SZ", "quantity": 900}]},
        ticks=_tick(),
    )
    assert plan["side"] == "SELL"
    assert plan["stock_code"] == "160723.SZ"


def test_same_day_or_pre_activation_signals_are_not_executable():
    with pytest.raises(SimulationExecutionBlocked):
        build_order_plan(
            signal_event=_event(day="20260911"), activation_signal_not_before="20260911", trade_day="20260911",
            sleeve_summary={"cash": 100000, "positions": []}, ticks=_tick(),
        )
    with pytest.raises(SimulationExecutionBlocked):
        build_order_plan(
            signal_event=_event(day="20260910"), activation_signal_not_before="20260911", trade_day="20260914",
            sleeve_summary={"cash": 100000, "positions": []}, ticks=_tick(),
        )
