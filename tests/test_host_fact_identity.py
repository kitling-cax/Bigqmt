import json

import pytest

from kitling_bigqmt.host_fact_identity import (
    HostFactIdentityError,
    credential_document,
    generate_credential,
    load_credentials,
    trusted_hosts_from_file,
)


def test_generate_and_load_supports_rotation_overlap(tmp_path):
    active = generate_credential("host-105", key_id="host-105-fact-v1")
    next_credential = generate_credential("host-105", key_id="host-105-fact-v2")
    path = tmp_path / "fact-identities.json"
    path.write_text(json.dumps(credential_document([active, next_credential])), encoding="utf-8")
    loaded = load_credentials(path)
    assert [item.key_id for item in loaded] == ["host-105-fact-v1", "host-105-fact-v2"]
    assert set(trusted_hosts_from_file(path)) == {"host-105-fact-v1", "host-105-fact-v2"}


def test_revoked_identity_is_not_trusted_and_malformed_secret_fails(tmp_path):
    credential = generate_credential("host-105", key_id="host-105-fact-v1")
    revoked = {**credential_document([credential])["hosts"][0], "status": "REVOKED"}
    path = tmp_path / "revoked.json"
    path.write_text(json.dumps({"schema_version": 1, "hosts": [revoked]}), encoding="utf-8")
    with pytest.raises(HostFactIdentityError, match="no active"):
        load_credentials(path)
    path.write_text(json.dumps({"schema_version": 1, "hosts": [{**revoked, "status": "ACTIVE", "secret_b64": "bad"}]}), encoding="utf-8")
    with pytest.raises(HostFactIdentityError, match="encoding"):
        load_credentials(path)


def test_credential_document_never_contains_plaintext_metadata_other_than_secret_file_payload():
    credential = generate_credential("host-105", key_id="host-105-fact-v1")
    document = credential_document([credential])
    assert document["schema_version"] == 1
    assert document["hosts"][0]["key_id"] == "host-105-fact-v1"
    assert len(document["hosts"][0]["secret_b64"]) >= 43
