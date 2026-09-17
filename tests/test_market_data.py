import unittest

from kitling_bigqmt.market_data import MarketDataFormatError, normalize_daily_bars


class MarketDataNormalizationTests(unittest.TestCase):
    def test_columnar_dataframe_envelope(self):
        response = {"ok": True, "data": {"511010.SH": {
            "__bigqmt_type__": "DataFrame",
            "columns": ["stime", "close", "preClose", "suspendFlag"],
            "records": {
                "time": [1514822400000, 1514908800000],
                "stime": ["20180102", "20180103"],
                "close": [109.52, 109.564],
                "preClose": [109.386, 109.52],
                "suspendFlag": [0, 0],
            },
        }}}
        bars = normalize_daily_bars(response, "511010.SH")
        self.assertEqual(["20180102", "20180103"], [bar.trade_date for bar in bars])
        self.assertEqual(109.564, bars[-1].close)

    def test_row_list_envelope(self):
        response = {"ok": True, "data": {"159915.SZ": {
            "__bigqmt_type__": "DataFrame",
            "records": [
                {"time": 1514908800000, "close": 1.2, "preClose": 1.1, "suspendFlag": 0},
            ],
        }}}
        bars = normalize_daily_bars(response, "159915.SZ")
        self.assertEqual("20180102", bars[0].trade_date)

    def test_malformed_columnar_lengths_fail_closed(self):
        response = {"ok": True, "data": {"511010.SH": {
            "records": {"stime": ["20180102"], "close": []},
        }}}
        with self.assertRaises(MarketDataFormatError):
            normalize_daily_bars(response, "511010.SH")

    def test_duplicate_dates_fail_closed(self):
        response = {"ok": True, "data": {"511010.SH": {
            "records": [
                {"stime": "20180102", "close": 1},
                {"stime": "20180102", "close": 2},
            ],
        }}}
        with self.assertRaises(MarketDataFormatError):
            normalize_daily_bars(response, "511010.SH")


if __name__ == "__main__":
    unittest.main()
