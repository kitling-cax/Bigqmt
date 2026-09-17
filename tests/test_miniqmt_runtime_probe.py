from pathlib import Path

def test_miniqmt_probe_is_import_only():
    source=Path("scripts/probe_miniqmt_runtime.py").read_text(encoding="utf-8")
    assert "IMPORT_ONLY_NO_DATA_FETCH_NO_BROKER_CALL" in source
    assert '"data_fetch":False' in source
    assert "get_market_data_ex" in source
