"""Fail-closed (option B) semantics for machine.local.json runtime loaders.

A missing config/machine.local.json remains the supported fallback (empty dict).
A present-but-malformed file (invalid JSON or non-object) must raise
MachineLocalConfigError from every runtime loader entry point rather than
silently falling back to defaults.

Read-only unit tests; no QMT, Redis, or order path is touched.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kitling_bigqmt import machine_config as mc


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _bad_json(root: Path) -> Path:
    p = root / "config" / mc.MACHINE_LOCAL_FILENAME
    _write_text(p, "{ this is not valid json")
    return p


def _non_object(root: Path) -> Path:
    p = root / "config" / mc.MACHINE_LOCAL_FILENAME
    _write_text(p, "[1, 2, 3]")
    return p


def test_load_machine_local_missing_file_returns_empty(tmp_path):
    assert mc.load_machine_local(tmp_path) == {}


def test_load_machine_local_bad_json_raises(tmp_path):
    _bad_json(tmp_path)
    with pytest.raises(mc.MachineLocalConfigError):
        mc.load_machine_local(tmp_path)


def test_load_machine_local_non_object_raises(tmp_path):
    _non_object(tmp_path)
    with pytest.raises(mc.MachineLocalConfigError):
        mc.load_machine_local(tmp_path)


def test_load_gateway_bad_machine_local_raises(tmp_path):
    _bad_json(tmp_path)
    with pytest.raises(mc.MachineLocalConfigError):
        mc.load_gateway(tmp_path, "simulation")


def test_load_tray_profiles_bad_machine_local_raises(tmp_path):
    _bad_json(tmp_path)
    with pytest.raises(mc.MachineLocalConfigError):
        mc.load_tray_profiles(tmp_path)


def test_effective_config_bad_machine_local_raises(tmp_path):
    _bad_json(tmp_path)
    with pytest.raises(mc.MachineLocalConfigError):
        mc.effective_config(tmp_path, "simulation")


def test_effective_config_non_object_raises(tmp_path):
    _non_object(tmp_path)
    with pytest.raises(mc.MachineLocalConfigError):
        mc.effective_config(tmp_path, "production_readonly")

