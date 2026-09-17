from pathlib import Path

def test_update_cycle_is_candidate_only_and_fail_closed():
    source = Path("scripts/run_unified_v2_update_cycle.py").read_text(encoding="utf-8")
    assert "CANDIDATE_PREFLIGHT_NO_GLOBAL_WRITE" in source
    assert "global_latest_updated\":False" in source
    assert "check_pit_v2_gate.py" in source
