import pandas as pd
from kitling_bigqmt.freshness_v2 import assess_source_freshness

def test_freshness_distinguishes_current_and_stale_sources():
    result = assess_source_freshness({"a": pd.DataFrame({"code":["A"],"trade_date":["20260911"]}), "b": pd.DataFrame({"code":["B"],"trade_date":["20260910"]})}, "20260911")
    assert result["sources"]["a"]["status"] == "PASSED"
    assert result["sources"]["b"]["status"] == "BLOCKED_STALE_OR_UNVERIFIED"
    assert result["all_sources_fresh"] is False
