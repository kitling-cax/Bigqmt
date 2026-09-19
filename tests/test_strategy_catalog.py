import hashlib
import json
from pathlib import Path

from kitling_bigqmt.strategy_catalog import list_candidates


def test_catalog_lists_verified_candidate(tmp_path: Path, monkeypatch):
    root = tmp_path / "strategies"
    package = root / "candidate" / "S10" / "v1.1.15" / "r1"
    payload = package / "payload"
    payload.mkdir(parents=True)
    source = payload / "strategy.py"
    source.write_text("print('safe')\n", encoding="utf-8")
    manifest = {
        "schema_version": 1, "strategy_id": "S10", "version": "v1.1.15", "build_id": "r1",
        "artifacts": [{"path": "payload/strategy.py", "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                       "size": source.stat().st_size}],
        "safety": {"orders_enabled": False, "formal_account_allowed": False},
    }
    (package / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("BIGQMT_STRATEGY_LIBRARY_ROOT", str(root))
    result = list_candidates(tmp_path)
    assert result["library_available"] is True
    assert result["candidates"][0]["status"] == "READY"
    assert result["push_supported"] is False


def test_catalog_rejects_unsafe_flags(tmp_path: Path, monkeypatch):
    root = tmp_path / "strategies" / "x"
    root.mkdir(parents=True)
    (root / "MANIFEST.json").write_text(json.dumps({
        "strategy_id": "S", "version": "v1", "build_id": "r1", "artifacts": [{"path": "none"}],
        "safety": {"orders_enabled": True, "formal_account_allowed": False},
    }), encoding="utf-8")
    monkeypatch.setenv("BIGQMT_STRATEGY_LIBRARY_ROOT", str(tmp_path / "strategies"))
    assert list_candidates(tmp_path)["candidates"][0]["status"] == "INVALID"
