import unittest

from kitling_bigqmt.v1_1_15_reproduction import (
    FALLBACK_PTRADE,
    close_signal,
    legacy_weighted_momentum,
    new_state,
    virtual_fill,
)


class V115ReproductionTests(unittest.TestCase):
    def test_momentum_requires_exact_completed_window(self):
        self.assertIsNone(legacy_weighted_momentum([1.0] * 24))
        self.assertIsNone(legacy_weighted_momentum([1.0] * 25))  # zero variance -> no R2

    def test_empty_sleeve_selects_best_sma_candidate(self):
        market = {
            "518880.SS": {"adjusted": [100.0 + i * 0.1 for i in range(25)], "raw": [100.0]},
            FALLBACK_PTRADE: {"adjusted": [], "raw": [100.0]},
        }
        state = new_state()
        signal = close_signal(state, market, "20260908")
        self.assertEqual("518880.SS", signal["desired"])
        self.assertEqual("EMPTY_TO_BEST_SMA4", signal["reason"])
        self.assertEqual("518880.SS", state["pending_target"])

    def test_empty_sleeve_falls_back_when_no_candidate_score(self):
        state = new_state()
        signal = close_signal(state, {FALLBACK_PTRADE: {"raw": [100.0]}}, "20260908")
        self.assertEqual(FALLBACK_PTRADE, signal["desired"])
        self.assertEqual("EMPTY_TO_FALLBACK", signal["reason"])

    def test_virtual_fill_is_explicit_state_transition(self):
        state = new_state()
        state["pending_target"] = "518880.SS"
        state["signal_day"] = "20260908"
        fill = virtual_fill(state, "20260909", 101.0)
        self.assertEqual("518880.SS", fill["to"])
        self.assertEqual("518880.SS", state["current"])
        self.assertIsNone(state["pending_target"])


if __name__ == "__main__":
    unittest.main()
