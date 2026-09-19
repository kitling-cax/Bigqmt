import hashlib
import json
from pathlib import Path

from kitling_bigqmt.strategy_catalog import catalog_html, list_candidates, preview_push


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

    preview = preview_push(
        tmp_path,
        "S10",
        "v1.1.15",
        "r1",
        ["192.168.1.125", "10.10.10.113"],
        [{"host_id": "192.168.1.125", "state": "HEALTHY_READONLY", "sent_at": "now"}],
    )
    assert preview["status"] == "PREVIEW_ONLY"
    assert preview["assignment_created"] is False
    assert preview["install_started"] is False
    assert preview["targets"][0]["status"] == "READY_TO_PULL"
    assert preview["targets"][1]["status"] == "HOST_NOT_CONNECTED"


def test_catalog_rejects_unsafe_flags(tmp_path: Path, monkeypatch):
    root = tmp_path / "strategies" / "x"
    root.mkdir(parents=True)
    (root / "MANIFEST.json").write_text(json.dumps({
        "strategy_id": "S", "version": "v1", "build_id": "r1", "artifacts": [{"path": "none"}],
        "safety": {"orders_enabled": True, "formal_account_allowed": False},
    }), encoding="utf-8")
    monkeypatch.setenv("BIGQMT_STRATEGY_LIBRARY_ROOT", str(tmp_path / "strategies"))
    assert list_candidates(tmp_path)["candidates"][0]["status"] == "INVALID"


def test_catalog_page_is_readonly_and_has_no_push_action():
    page = catalog_html()
    assert "BigQMT 私有策略库" in page
    assert "生成推送预览" in page
    assert "/api/v1/strategy-push-preview" in page
    assert "不安装、不创建租约" in page
    assert "orders_enabled=false" in page


def test_preview_rejects_unknown_candidate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BIGQMT_STRATEGY_LIBRARY_ROOT", str(tmp_path / "empty"))
    try:
        preview_push(tmp_path, "missing", "v1", "r1", [".125"], [])
    except ValueError as exc:
        assert str(exc) == "strategy candidate not found"
    else:
        raise AssertionError("unknown candidate must be rejected")
