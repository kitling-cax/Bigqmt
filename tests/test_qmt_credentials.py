import sys
import types

from kitling_bigqmt import qmt_credentials


def test_write_passes_unicode_blob_to_pywin32(monkeypatch):
    recorded = {}

    fake = types.SimpleNamespace(
        CRED_TYPE_GENERIC=1,
        CRED_PERSIST_LOCAL_MACHINE=2,
        CredWrite=lambda item, flags: recorded.update(item=item, flags=flags),
    )
    monkeypatch.setitem(sys.modules, "win32cred", fake)
    qmt_credentials.write("simulation", "90000001", "not-a-real-password")
    assert recorded["item"]["CredentialBlob"] == "not-a-real-password"
    assert isinstance(recorded["item"]["CredentialBlob"], str)
