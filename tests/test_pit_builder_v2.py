import pandas as pd
import pytest
from kitling_bigqmt.pit_builder_v2 import PitBuilderV2Error, build_split_only_pit

def _raw():
    return pd.DataFrame([{"code":"E","trade_date":"20260101","open":1,"high":1,"low":1,"close":1,"raw_volume":1,"raw_amount":1,"received_at":"2026-01-01T07:10:00+00:00"},{"code":"E","trade_date":"20260102","open":1,"high":1,"low":1,"close":1,"raw_volume":1,"raw_amount":1,"received_at":"2026-01-02T07:10:00+00:00"}])

def test_split_pit_rebuilds_factor_from_verified_action():
    actions=pd.DataFrame([{"code":"E","ex_date":"20260102","qmt_bonus_ratio":1,"available_at":"2026-01-03T01:30:00+00:00","numeric_status":"VERIFIED_SPLIT_RATIO"}])
    frame, checks=build_split_only_pit(_raw(),actions,"r")
    assert frame.iloc[-1]["close"]==2
    assert checks["pit_ready"] is True

def test_unverified_action_is_rejected():
    actions=pd.DataFrame([{"code":"E","ex_date":"20260102","qmt_bonus_ratio":1,"available_at":None,"numeric_status":"UNVERIFIED"}])
    with pytest.raises(PitBuilderV2Error, match="VERIFIED_SPLIT_RATIO"):
        build_split_only_pit(_raw(),actions,"r")
