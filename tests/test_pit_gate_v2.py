from kitling_bigqmt.pit_gate_v2 import evaluate_pit_inputs

def test_pit_gate_blocks_provisional_raw_and_unverified_actions():
    result=evaluate_pit_inputs({"status":"PUBLISHED_ISOLATED_SILVER_RAW_CANDIDATE","global_publishable":False,"release_id":"r"},{"numeric_factor_gate":"BLOCKED_UNVERIFIED","available_at_gate":"BLOCKED_DATE_ONLY","release_id":"a"})
    assert result["publishable"] is False
    assert result["decision"] == "BLOCKED_PIT_V2"
    assert "corporate_actions_numeric" in result["failed_gates"]
