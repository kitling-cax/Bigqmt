import json
from pathlib import Path

import pytest

from kitling_bigqmt import machine_config as mc


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _schema(root: Path) -> Path:
    src = mc.project_root() / "config" / "schemas" / mc.MACHINE_LOCAL_SCHEMA_FILENAME
    dst = root / "config" / "schemas" / mc.MACHINE_LOCAL_SCHEMA_FILENAME
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return dst


def _gateway(root: Path, profile: str, **overrides) -> None:
    env = "simulation" if profile == "simulation" else "production_readonly"
    account = "90000001" if profile == "simulation" else "90000002"
    base = {
        "environment": env,
        "account_id": account,
        "redis": {"host": "127.0.0.1", "port": 6379, "db": 5, "password": ""},
        "state_db": str(root / "runtime_data" / "state" / env / "qmt_runtime.sqlite3"),
        "audit_dir": str(root / "runtime_data" / "audit" / env),
    }
    base.update(overrides)
    _write(root / "config" / f"host_gateway.{env}.json", base)


def _tray(root: Path, profile: str, **overrides) -> None:
    _write(
        root / "config" / "tray_profiles.json",
        {
            "profiles": {
                profile: {
                    "qmt_root": "C:/BigQMT/work/somewhere",
                    "orders_enabled": False,
                    "redis": {"host": "127.0.0.1", "port": 6379, "db": 5},
                    "dashboard": {"enabled": True, "port": 17890, "route": "/overview"},
                    "qmt_launch": {"ready_port": 58600},
                    **overrides,
                }
            }
        },
    )


@pytest.fixture()
def secrets_clean(monkeypatch):
    monkeypatch.delenv("BIGQMT_COORDINATOR_ENDPOINT", raising=False)
    monkeypatch.delenv("BIGQMT_HOST_ID", raising=False)
    return monkeypatch


def test_validate_machine_local_missing_file_is_fallback_ok(tmp_path):
    _schema(tmp_path)
    assert mc.validate_machine_local(tmp_path) == []


def test_validate_machine_local_rejects_bad_json(tmp_path):
    _schema(tmp_path)
    p = tmp_path / "config" / mc.MACHINE_LOCAL_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    errors = mc.validate_machine_local(tmp_path)
    assert errors
    assert any("not a valid JSON" in e for e in errors)


def test_validate_machine_local_rejects_non_object(tmp_path):
    _schema(tmp_path)
    p = tmp_path / "config" / mc.MACHINE_LOCAL_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1, 2, 3]", encoding="utf-8")
    errors = mc.validate_machine_local(tmp_path)
    assert any("must be a JSON object" in e for e in errors)


def test_validate_machine_local_rejects_bad_schema_version(tmp_path):
    _schema(tmp_path)
    _write(tmp_path / "config" / mc.MACHINE_LOCAL_FILENAME, {"schema_version": 0})
    errors = mc.validate_machine_local(tmp_path)
    assert errors
    assert any("schema_version" in e for e in errors)


def test_validate_machine_local_accepts_valid_partial_override(tmp_path):
    _schema(tmp_path)
    _write(
        tmp_path / "config" / mc.MACHINE_LOCAL_FILENAME,
        {
            "schema_version": 1,
            "data_directory": str(tmp_path / "BigQMT_Data"),
            "environments": {
                "simulation": {
                    "qmt_root": str(tmp_path / "QMT_SIM"),
                    "redis": {"host": "10.0.0.2", "port": 7000, "db": 9},
                    "dashboard_port": 18000,
                }
            },
        },
    )
    assert mc.validate_machine_local(tmp_path) == []


def test_effective_config_simulation_orders_disabled(tmp_path, secrets_clean):
    _schema(tmp_path)
    _gateway(tmp_path, "simulation")
    _tray(tmp_path, "simulation", orders_enabled=False)
    ec = mc.effective_config(tmp_path, "simulation")
    assert ec["environment"] == "simulation"
    assert ec["orders_enabled"] is False
    assert ec["redis"]["port"] == 6379
    assert ec["dashboard_port"] == 17890
    assert ec["ready_port"] == 58600
    assert ec["state_db"].startswith(str(tmp_path.resolve()))


def test_effective_config_production_maps_environment(tmp_path, secrets_clean):
    _schema(tmp_path)
    _gateway(tmp_path, "production_readonly")
    _tray(tmp_path, "production_readonly", orders_enabled=False)
    ec = mc.effective_config(tmp_path, "production_readonly")
    assert ec["environment"] == "production_readonly"
    assert ec["orders_enabled"] is False


def test_effective_config_hash_deterministic_and_overrides_change_it(tmp_path, secrets_clean):
    _schema(tmp_path)
    _gateway(tmp_path, "simulation")
    _tray(tmp_path, "simulation")
    first = mc.effective_config_hash(tmp_path, "simulation")
    second = mc.effective_config_hash(tmp_path, "simulation")
    assert first == second

    _write(
        tmp_path / "config" / mc.MACHINE_LOCAL_FILENAME,
        {"schema_version": 1, "data_directory": str(tmp_path / "Elsewhere")},
    )
    changed = mc.effective_config_hash(tmp_path, "simulation")
    assert changed != first


def test_audit_hardcoded_paths_finds_local_paths_and_ports(tmp_path):
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "inventory.txt").write_text(
        r"""install_root: C:\BigQMT\work\QMT_SIM
dashboard_port: 17890
nas_share: \\192.0.2.236\truenas
""",
        encoding="utf-8",
    )
    report = mc.audit_hardcoded_paths(tmp_path)
    assert report["finding_count"] > 0
    kinds = {f["kind"] for f in report["findings"]}
    values = {f.get("value") for f in report["findings"]}
    assert "absolute_path" in kinds
    assert "port" in kinds
    assert "unc_path" in kinds
    assert any(v == "17890" for v in values)
    assert any(v == r"C:\BigQMT\work\QMT_SIM" for v in values)
