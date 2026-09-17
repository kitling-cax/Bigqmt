import json

import pytest

from kitling_bigqmt import machine_config as mc


def test_private_config_is_explicit_and_local_runtime_does_not_depend_on_nas(tmp_path):
    remote = tmp_path / "nas" / "host.json"
    remote.parent.mkdir(parents=True)
    remote.write_text(json.dumps({"coordinator": {"endpoint": "http://nas.example:18443", "host_id": "host-nas"}, "data_directory": "D:/nas-data", "environments": {"simulation": {"account_id": "90000099"}}}), encoding="utf-8")
    local = tmp_path / "config" / "machine.local.json"
    local.parent.mkdir(parents=True)
    local.write_text(json.dumps({"coordinator": {"host_id": "host-local"}}), encoding="utf-8")
    remote.unlink()
    assert mc.load_machine_local(tmp_path)["coordinator"]["host_id"] == "host-local"


def test_private_config_rejects_secret_fields(tmp_path):
    remote = tmp_path / "host.json"
    remote.write_text(json.dumps({"redis": {"password": "must-not-be-here"}}), encoding="utf-8")
    with pytest.raises(mc.MachineLocalConfigError, match="forbidden secret"):
        mc._load_private_file(remote)


def test_private_config_environment_override(tmp_path, monkeypatch):
    remote = tmp_path / "host.json"
    remote.write_text(json.dumps({"coordinator": {"host_id": "env-host"}}), encoding="utf-8")
    assert mc.load_private_config(remote)["coordinator"]["host_id"] == "env-host"
