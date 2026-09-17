"""Protected-file lifecycle for Host Agent fact-signing identities.

Fact transport credentials are separate from simulation/production execution
Keys. This module never prints secret material and never puts it in a release
manifest. The actual file must be delivered through the host/container Secret
mechanism and kept outside the project checkout/NAS release tree.
"""
from __future__ import annotations

import base64
import json
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .coordinator_fact_auth import TrustedFactHost


class HostFactIdentityError(RuntimeError):
    pass


@dataclass(frozen=True)
class HostFactCredential:
    host_id: str
    key_id: str
    secret: bytes
    status: str = "ACTIVE"

    def trusted(self) -> TrustedFactHost:
        return TrustedFactHost(self.host_id, self.key_id, self.secret)


def generate_credential(host_id: str, *, key_id: str | None = None) -> HostFactCredential:
    if not host_id.strip():
        raise HostFactIdentityError("host_id is required")
    return HostFactCredential(host_id.strip(), key_id or (host_id.strip() + "-fact-" + uuid.uuid4().hex[:12]), secrets.token_bytes(32))


def _decode_secret(value: object) -> bytes:
    try:
        secret = base64.b64decode(str(value), validate=True)
    except (ValueError, TypeError, base64.binascii.Error) as exc:
        raise HostFactIdentityError("invalid fact signing secret encoding") from exc
    if len(secret) < 32:
        raise HostFactIdentityError("fact signing secret must be at least 32 bytes")
    return secret


def load_credentials(path: str | Path) -> list[HostFactCredential]:
    """Load active/next credentials from a protected secret file."""
    secret_path = Path(path)
    try:
        document = json.loads(secret_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HostFactIdentityError("cannot read fact identity secret file") from exc
    if document.get("schema_version") != 1 or not isinstance(document.get("hosts"), list):
        raise HostFactIdentityError("invalid fact identity secret file")
    result: list[HostFactCredential] = []
    key_ids: set[str] = set()
    for item in document["hosts"]:
        if not isinstance(item, dict):
            raise HostFactIdentityError("invalid fact identity entry")
        key_id, host_id, status = str(item.get("key_id") or "").strip(), str(item.get("host_id") or "").strip(), str(item.get("status") or "ACTIVE").upper()
        if not key_id or not host_id or key_id in key_ids or status not in {"ACTIVE", "NEXT", "REVOKED"}:
            raise HostFactIdentityError("invalid or duplicate fact identity entry")
        key_ids.add(key_id)
        if status != "REVOKED":
            result.append(HostFactCredential(host_id, key_id, _decode_secret(item.get("secret_b64")), status))
    if not result:
        raise HostFactIdentityError("no active fact identity is configured")
    return result


def trusted_hosts_from_file(path: str | Path) -> dict[str, TrustedFactHost]:
    return {credential.key_id: credential.trusted() for credential in load_credentials(path) if credential.status in {"ACTIVE", "NEXT"}}


def credential_document(credentials: list[HostFactCredential]) -> dict[str, Any]:
    """Serialize metadata for a protected secret file without exposing a hash or log output."""
    return {
        "schema_version": 1,
        "hosts": [{
            "host_id": item.host_id,
            "key_id": item.key_id,
            "status": item.status,
            "secret_b64": base64.b64encode(item.secret).decode("ascii"),
        } for item in credentials],
    }
