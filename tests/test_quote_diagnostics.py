import unittest

from kitling_bigqmt.quote_diagnostics import inspect_tick


class QuoteDiagnosticsTests(unittest.TestCase):
    def test_fresh_active_tick_is_allowed(self):
        tick = {"timetag": "20260908 10:30:00", "stockStatus": 3, "amount": 1, "volume": 1,
                "askPrice": [1, 0, 0, 0, 0], "bidPrice": [1, 0, 0, 0, 0]}
        result = inspect_tick("511010.SH", tick, "2026-09-08T02:30:10+00:00", 180)
        self.assertEqual("ALLOWED", result["admission"])
        self.assertEqual(["HEALTHY_SNAPSHOT"], result["observations"])

    def test_stale_empty_tick_is_blocked_without_status_interpretation(self):
        tick = {"timetag": "20260908 09:15:01", "stockStatus": 7, "amount": 0, "volume": 0,
                "askPrice": [0, 0, 0, 0, 0], "bidPrice": [0, 0, 0, 0, 0]}
        result = inspect_tick("513100.SH", tick, "2026-09-08T02:30:10+00:00", 180)
        self.assertEqual("BLOCKED", result["admission"])
        self.assertEqual(7, result["stock_status_observed"])
        self.assertIn("STALE_OR_UNKNOWN_TIMETAG", result["observations"])
        self.assertIn("ZERO_TRADE_ACTIVITY", result["observations"])
        self.assertIn("EMPTY_FIVE_LEVEL_BOOK", result["observations"])
