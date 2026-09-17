import pandas as pd
import pytest
from kitling_bigqmt.universe_pit_v2 import build_membership_rows, validate_universe

def test_universe_requires_explicit_forward_start_and_timezone():
    frame=build_membership_rows(["510300.SH","510300.SH"],"etf","20260912","2026-09-12T09:30:00+08:00","test","r")
    assert len(frame)==1
    assert validate_universe(frame)["status"]=="FORWARD_ONLY_CANDIDATE_NOT_HISTORICAL"
    with pytest.raises(ValueError, match="timezone"):
        build_membership_rows(["A"],"stock","20260912","2026-09-12T09:30:00","test","r")
