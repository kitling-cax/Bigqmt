"""Pure unit tests for the offline v1.1.15 switch rehearsal."""

from __future__ import annotations

import unittest

from kitling_bigqmt.switch_rehearsal import (
    MINIMUM_HOLD_DAYS,
    REHEARSAL_REASON,
    holding_guard_view,
    rehearse_switch,
)


TRADING = ["20260910", "20260911", "20260914", "20260915", "20260916", "20260917", "20260918"]
FILL_TIME = "1789093235"  # 2026-09-11 10:20:35 +08:00
ACTIVATION = "20260909"


def _ticks(code_to_price: dict[str, float]) -> dict[str, dict[str, float]]:
    return {code: {"lastPrice": float(price), "bidPrice": [float(price)], "askPrice": [float(price)]}
            for code, price in code_to_price.items()}


def _fill(code: str, quantity: int, price: float = 2.36) -> dict:
    return {"stock_code": code, "side": "BUY", "quantity": int(quantity),
            "price": float(price), "fee": float(quantity * price * 0.0001),
            "fill_time": FILL_TIME, "fill_id": "test-%s-%d" % (code, int(quantity))}


class HoldingGuardTests(unittest.TestCase):
    def test_entry_day_counting_is_real_fill(self) -> None:
        view = holding_guard_view(
            attributable_fills=[_fill("160723.SZ", 41400)],
            stock_code="160723.SZ", signal_day="20260916", trading_days=TRADING,
        )
        self.assertEqual(view["entry_day"], "20260911")
        self.assertEqual(view["actual_hold_days"], 4)
        self.assertEqual(view["minimum_hold_days"], MINIMUM_HOLD_DAYS)
        self.assertEqual(view["status"], "HELD")

    def test_entry_day_fifth_session_releases(self) -> None:
        view = holding_guard_view(
            attributable_fills=[_fill("160723.SZ", 41400)],
            stock_code="160723.SZ", signal_day="20260917", trading_days=TRADING,
        )
        self.assertEqual(view["status"], "ALLOWED")
        self.assertEqual(view["actual_hold_days"], 5)

    def test_no_open_fill_returns_no_open_marker(self) -> None:
        # BUY 100 on fill_time=FILL_TIME, SELL 100 strictly later -> flat sleeve.
        later = "1789093236"
        view = holding_guard_view(
            attributable_fills=[
                _fill("160723.SZ", 100),
                {"stock_code": "160723.SZ", "side": "SELL", "quantity": 100,
                 "price": 2.36, "fee": 0.1, "fill_time": later, "fill_id": "close-out"},
            ],
            stock_code="160723.SZ", signal_day="20260917", trading_days=TRADING,
        )
        self.assertEqual(view["status"], "NO_OPEN_REAL_FILL")


class SwitchRehearsalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sleeve = {
            "strategy_id": "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15",
            "cash": 2259.4866, "positions": [{"stock_code": "160723.SZ", "quantity": 41400, "cost_amount": 97740.51336}],
        }
        self.fills = [_fill("160723.SZ", 41400)]
        self.ticks = _ticks({"160723.SZ": 2.356, "162411.SZ": 1.031})

    def test_blocked_holding_guard_short_circuits(self) -> None:
        report = rehearse_switch(
            sleeve_summary=self.sleeve, attributable_fills=self.fills, ticks=self.ticks,
            signal_day="20260916", trade_day="20260917", trading_days=TRADING,
            activation_signal_not_before=ACTIVATION, desired_qmt="162411.SZ",
        )
        self.assertEqual(report["verdict"], "SWITCH_NOT_AVAILABLE_BLOCKED")
        self.assertEqual(report["sell_leg"]["status"], "BLOCKED")
        self.assertEqual(report["buy_leg"]["status"], "NOT_REHEARSED")
        self.assertEqual(report["holding_guard"]["status"], "HELD")
        self.assertFalse(report["second_invocation_required"])

    def test_allowed_holding_rehearses_both_legs(self) -> None:
        # QMT only publishes the calendar up to today, so the rehearsal must
        # state that the projected session is a trading day.
        report = rehearse_switch(
            sleeve_summary=self.sleeve, attributable_fills=self.fills, ticks=self.ticks,
            signal_day="20260917", trade_day="20260918", trading_days=TRADING,
            activation_signal_not_before=ACTIVATION, desired_qmt="162411.SZ",
            assume_trade_day_is_trading=True,
        )
        self.assertEqual(report["verdict"], "SWITCH_REHEARSED_OK")
        self.assertEqual(report["sell_leg"]["status"], "PLAN")
        self.assertEqual(report["sell_leg"]["plan"]["side"], "SELL")
        self.assertEqual(report["sell_leg"]["plan"]["stock_code"], "160723.SZ")
        self.assertEqual(report["sell_leg"]["plan"]["quantity"], 41400)
        self.assertEqual(report["buy_leg"]["status"], "PLAN")
        self.assertEqual(report["buy_leg"]["plan"]["side"], "BUY")
        self.assertEqual(report["buy_leg"]["plan"]["stock_code"], "162411.SZ")
        self.assertTrue(report["second_invocation_required"])
        self.assertTrue(report["signal_ids_distinct"])
        self.assertNotEqual(report["sell_leg"]["plan"]["signal_id"],
                            report["buy_leg"]["plan"]["signal_id"])
        self.assertEqual(report["sell_leg"]["plan"]["reason"], REHEARSAL_REASON)

    def test_previous_close_after_flat_close_buys_next_session(self) -> None:
        # A flat sleeve + a previous-close signal lands as a single buy leg
        # on the next session, no sell required, no second invocation.
        report = rehearse_switch(
            sleeve_summary={"strategy_id": "x", "cash": 100000.0, "positions": []},
            attributable_fills=[], ticks=self.ticks,
            signal_day="20260917", trade_day="20260918", trading_days=TRADING,
            activation_signal_not_before=ACTIVATION, desired_qmt="162411.SZ",
            assume_trade_day_is_trading=True,
        )
        self.assertEqual(report["verdict"], "SINGLE_BUY_LEG_REHEARSED_OK")
        self.assertEqual(report["buy_leg"]["status"], "PLAN")
        self.assertEqual(report["buy_leg"]["plan"]["side"], "BUY")
        self.assertFalse(report["second_invocation_required"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
