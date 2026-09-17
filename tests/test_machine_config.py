import json
from pathlib import Path

from kitling_bigqmt import machine_config as mc


def _write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _gateway(root: Path, **overrides):
    base = {
        "environment": "simulation",
        "account_id": "90000001",
        "redis": {"host": "127.0.0.1", "port": 6379, "db": 5, "password": ""},
        "state_db": str(root / "runtime_data" / "state" / "simulation" / "qmt_runtime.sqlite3"),
        "audit_dir": str(root / "runtime_data" / "audit" / "simulation"),
    }
    base.update(overrides)
    _write(root / "config" / "host_gateway.simulation.json", base)


def test_default_fallback_to_absolute_paths(tmp_path):
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    _gateway(root)
    assert not (root / "config" / "machine.local.json").exists()
    gw = mc.load_gateway(root, "simulation")
    assert gw["state_db"] == str((root / "runtime_data" / "state" / "simulation" / "qmt_runtime.sqlite3").resolve())
    assert gw["audit_dir"] == str((root / "runtime_data" / "audit" / "simulation").resolve())
    assert gw["redis"]["port"] == 6379


def test_relative_paths_resolve_against_runtime_data(tmp_path):
    root = tmp_path / "proj"
    _gateway(
        root,
        state_db="state/simulation/qmt_runtime.sqlite3",
        audit_dir="audit/simulation",
    )
    same = mc.load_gateway(root, "simulation")
    rel = mc.load_gateway(root, "simulation")
    assert rel["state_db"] == str((root / "runtime_data" / "state" / "simulation" / "qmt_runtime.sqlite3").resolve())
    assert rel["audit_dir"] == str((root / "runtime_data" / "audit" / "simulation").resolve())
    assert same["state_db"] == rel["state_db"]


def test_data_directory_relocation(tmp_path):
    root = tmp_path / "proj"
    new_data = tmp_path / "BigQMT_Data"
    _write(root / "config" / "machine.local.json", {"data_directory": str(new_data)})
    _gateway(root)
    gw = mc.load_gateway(root, "simulation")
    assert gw["state_db"] == str((new_data / "state" / "simulation" / "qmt_runtime.sqlite3").resolve())
    assert gw["audit_dir"] == str((new_data / "audit" / "simulation").resolve())


def test_redis_and_port_override(tmp_path):
    root = tmp_path / "proj"
    qmt_root = tmp_path / "QMT_SIM"
    _write(root / "config" / "machine.local.json", {
        "environments": {
            "simulation": {
                "qmt_root": str(qmt_root),
                "redis": {"host": "10.0.0.2", "port": 7000, "db": 9},
                "dashboard_port": 18000,
                "ready_port": 59000,
            }
        }
    })
    _write(root / "config" / "tray_profiles.json", {
        "profiles": {
            "simulation": {
                "qmt_root": "F:/old_path",
                "redis": {"host": "127.0.0.1", "port": 6379, "db": 5},
                "dashboard": {"enabled": True, "port": 17890, "route": "/simulation/overview"},
                "qmt_launch": {"ready_port": 58600},
            }
        }
    })
    profiles = mc.load_tray_profiles(root)["profiles"]
    sim = profiles["simulation"]
    assert sim["qmt_root"] == str(qmt_root.resolve())
    assert sim["redis"] == {"host": "10.0.0.2", "port": 7000, "db": 9}
    assert sim["dashboard"]["port"] == 18000
    assert sim["qmt_launch"]["ready_port"] == 59000


def test_missing_machine_local_keeps_tray_profile_defaults(tmp_path):
    root = tmp_path / "proj"
    _write(root / "config" / "tray_profiles.json", {
        "profiles": {
            "simulation": {
                "qmt_root": "C:/BigQMT/work/国金QMT交易端模拟",
                "redis": {"host": "127.0.0.1", "port": 6379, "db": 5},
                "dashboard": {"enabled": True, "port": 17890, "route": "/simulation/overview"},
            }
        }
    })
    profiles = mc.load_tray_profiles(root)["profiles"]
    assert profiles["simulation"]["qmt_root"] == "C:/BigQMT/work/国金QMT交易端模拟"
    assert profiles["simulation"]["dashboard"]["port"] == 17890

