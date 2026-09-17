import pandas as pd
from kitling_bigqmt.corporate_actions_v2 import build_action_rows

def test_action_candidate_preserves_unverified_factor_and_date_only_availability():
    rows = build_action_rows({"events":[{"code":"510300.SH","qmt_event_date":"20260701","qmt_payload":[0,1,0,0,0,0,2],"event_date_match":True,"numeric_factor_status":"UNVERIFIED"}]},{"510300.SH"},"r")
    assert rows[0]["asset_class"] == "etf"
    assert rows[0]["available_at"] is None
    assert rows[0]["qmt_cumulative_factor"] == 2
    assert rows[0]["numeric_status"] == "UNVERIFIED"
