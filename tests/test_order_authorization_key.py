import sys
import types

import pytest

from kitling_bigqmt import order_authorization_key as keys


class MissingCredential(Exception):
    pass


def _fake_store(monkeypatch):
    values = {}

    def write(item, flags):
        del flags
        values[item["TargetName"]] = dict(item)

    def read(target, credential_type):
        del credential_type
        if target not in values:
            raise MissingCredential("1168 not found")
        return dict(values[target])

    def delete(target, credential_type, flags):
        del credential_type, flags
        if target not in values:
            raise MissingCredential("1168 not found")
        del values[target]

    fake = types.SimpleNamespace(
        CRED_TYPE_GENERIC=1,
        CRED_PERSIST_LOCAL_MACHINE=2,
        CredWrite=write,
        CredRead=read,
        CredDelete=delete,
    )
    monkeypatch.setitem(sys.modules, "win32cred", fake)
    return values


def test_key_is_account_scoped_and_never_returned(monkeypatch):
    _fake_store(monkeypatch)
    secret = "simulation-key-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    result = keys.write("simulation", "90000001", secret)
    assert result["valid"] is True
    assert result["state"] == "VALID"
    assert result["fingerprint"].startswith("sha256:")
    assert secret not in str(result)
    mismatch = keys.status("simulation", "90000002")
    assert mismatch["valid"] is False
    assert mismatch["state"] == "ACCOUNT_MISMATCH"


def test_missing_and_delete_are_fail_closed_and_idempotent(monkeypatch):
    _fake_store(monkeypatch)
    assert keys.status("production_readonly", "90000002")["state"] == "MISSING"
    keys.delete("production_readonly")
    keys.write("production_readonly", "90000002", "P" * 32)
    keys.delete("production_readonly")
    keys.delete("production_readonly")
    assert keys.status("production_readonly", "90000002")["valid"] is False


def test_weak_key_is_rejected(monkeypatch):
    _fake_store(monkeypatch)
    with pytest.raises(keys.OrderAuthorizationKeyError, match="10"):
        keys.write("simulation", "90000001", "too-short")
