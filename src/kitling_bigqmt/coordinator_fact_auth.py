"""Signed, time-bounded Host Agent fact-upload envelopes.

This module protects operational facts only.  It is deliberately separate
from account execution-Key policy and does not grant a lease or order right.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping


class FactAuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrustedFactHost:
    host_id: str
    key_id: str
    signing_secret: bytes


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _signing_payload(envelope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": envelope.get("schema_version"),
        "host_id": envelope.get("host_id"),
        "key_id": envelope.get("key_id"),
        "request_id": envelope.get("request_id"),
        "issued_at_epoch": envelope.get("issued_at_epoch"),
        "expires_at_epoch": envelope.get("expires_at_epoch"),
        "body_sha256": envelope.get("body_sha256"),
    }


def build_signed_fact_envelope(
    host_id: str,
    key_id: str,
    signing_secret: bytes,
    body: dict[str, Any],
    *,
    now_epoch: float | None = None,
    ttl_seconds: float = 60.0,
    request_id: str | None = None,
) -> dict[str, Any]:
    moment = time.time() if now_epoch is None else float(now_epoch)
    if not host_id.strip() or not key_id.strip() or not signing_secret:
        raise FactAuthenticationError("host identity is incomplete")
    if ttl_seconds <= 0 or ttl_seconds > 300:
        raise FactAuthenticationError("invalid signed request TTL")
    result: dict[str, Any] = {
        "schema_version": 1,
        "host_id": host_id,
        "key_id": key_id,
        "request_id": request_id or str(uuid.uuid4()),
        "issued_at_epoch": moment,
        "expires_at_epoch": moment + float(ttl_seconds),
        "body_sha256": sha256_json(body),
        "body": body,
    }
    signature = hmac.new(signing_secret, canonical_json(_signing_payload(result)).encode("utf-8"), hashlib.sha256).hexdigest()
    result["signature"] = "hmac-sha256:" + signature
    return result


def verify_signed_fact_envelope(
    envelope: Mapping[str, Any],
    trusted_hosts: Mapping[str, TrustedFactHost],
    *,
    now_epoch: float | None = None,
    max_clock_skew_seconds: float = 15.0,
) -> TrustedFactHost:
    """Authenticate one envelope. Replay tracking is handled by the store."""
    moment = time.time() if now_epoch is None else float(now_epoch)
    if envelope.get("schema_version") != 1 or not isinstance(envelope.get("body"), dict):
        raise FactAuthenticationError("invalid fact envelope")
    key_id, host_id = str(envelope.get("key_id") or ""), str(envelope.get("host_id") or "")
    trusted = trusted_hosts.get(key_id)
    if trusted is None or trusted.host_id != host_id:
        raise FactAuthenticationError("untrusted Host Agent identity")
    try:
        uuid.UUID(str(envelope.get("request_id")))
        issued = float(envelope.get("issued_at_epoch"))
        expires = float(envelope.get("expires_at_epoch"))
    except (TypeError, ValueError) as exc:
        raise FactAuthenticationError("invalid signed request metadata") from exc
    if issued > moment + max_clock_skew_seconds or expires <= moment or expires <= issued:
        raise FactAuthenticationError("signed request is expired or outside clock window")
    body = envelope["body"]
    if envelope.get("body_sha256") != sha256_json(body):
        raise FactAuthenticationError("signed request body hash mismatch")
    signature = str(envelope.get("signature") or "")
    expected = "hmac-sha256:" + hmac.new(
        trusted.signing_secret, canonical_json(_signing_payload(envelope)).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise FactAuthenticationError("signed request signature mismatch")
    return trusted
