import json
from pathlib import Path


def test_lake_cycle_script_declares_read_only_boundary():
    source = Path("scripts/run_lake_cycle.py").read_text(encoding="utf-8")
    assert "contacts QMT/Redis" in source
    assert '"orders_enabled": False' in source
    assert '"broker_call_made": False' in source
    assert 'runtime_data" / "evidence"' in source


def test_tray_schedules_at_most_one_lake_cycle_attempt_per_day():
    source = Path("tray/BigQMTTray.ps1").read_text(encoding="utf-8")
    assert "LakeCycleHour = 16" in source
    assert "LakeCycleMinute = 10" in source
    assert "$script:lastLakeDate" in source
    assert "lake_cycle_auto" in source
