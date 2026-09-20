"""Account-scoped local order-authorization Key storage.

The plaintext Key is stored only in Windows Credential Manager.  Callers see
only presence, account binding and a SHA-256 fingerprint.  Possessing a valid
Key is a necessary order gate; it never bypasses strategy, runtime-window,
Coordinator or broker preflight checks.
"""

from __future__ import annotations

import hashlib
from typing import Any


SUPPORTED_PROFILES = {"simulation", "production_readonly"}
MINIMUM_KEY_LENGTH = 32


class OrderAuthorizationKeyError(RuntimeError):
    """Credential Manager is unavailable or rejected an operation."""


def target_name(profile: str) -> str:
    profile = str(profile).strip()
    if profile not in SUPPORTED_PROFILES:
        raise OrderAuthorizationKeyError("unsupported profile")
    return "KitlingBigQMT/OrderAuthorization/" + profile


def fingerprint(secret: str) -> str:
    return "sha256:" + hashlib.sha256(str(secret).encode("utf-8")).hexdigest()


def _decode_blob(blob: Any) -> str:
    if isinstance(blob, bytes):
        try:
            return blob.decode("utf-16-le")
        except UnicodeDecodeError:
            return blob.decode("utf-8")
    return str(blob or "")


def write(profile: str, account_id: str, secret: str) -> dict[str, Any]:
    account_id = str(account_id).strip()
    secret = str(secret)
    if not account_id:
        raise OrderAuthorizationKeyError("account_id is required")
    if len(secret.strip()) < MINIMUM_KEY_LENGTH:
        raise OrderAuthorizationKeyError("authorization Key must contain at least 32 characters")
    try:
        import win32cred

        win32cred.CredWrite({
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": target_name(profile),
            "UserName": account_id,
            "CredentialBlob": secret,
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
            "Comment": "BigQMT account order authorization; local only; never upload.",
        }, 0)
    except OrderAuthorizationKeyError:
        raise
    except Exception as exc:
        raise OrderAuthorizationKeyError("authorization Key could not be saved") from exc
    return status(profile, account_id)


def status(profile: str, expected_account_id: str | None = None) -> dict[str, Any]:
    expected = str(expected_account_id or "").strip()
    base = {
        "profile": str(profile),
        "account_id": expected,
        "installed": False,
        "valid": False,
        "fingerprint": "",
        "state": "MISSING",
        "orders_enabled": False,
    }
    try:
        import win32cred

        item: dict[str, Any] = win32cred.CredRead(target_name(profile), win32cred.CRED_TYPE_GENERIC)
        account_id = str(item.get("UserName") or "").strip()
        secret = _decode_blob(item.get("CredentialBlob"))
    except OrderAuthorizationKeyError:
        raise
    except Exception as exc:
        if "1168" in str(exc):
            return base
        return {**base, "state": "CREDENTIAL_STORE_UNAVAILABLE"}
    result = {
        **base,
        "account_id": account_id,
        "installed": True,
        "fingerprint": fingerprint(secret) if secret else "",
    }
    if not account_id or len(secret.strip()) < MINIMUM_KEY_LENGTH:
        return {**result, "state": "INVALID"}
    if expected and account_id != expected:
        return {**result, "state": "ACCOUNT_MISMATCH"}
    return {**result, "valid": True, "state": "VALID"}


def delete(profile: str) -> None:
    try:
        import win32cred

        win32cred.CredDelete(target_name(profile), win32cred.CRED_TYPE_GENERIC, 0)
    except OrderAuthorizationKeyError:
        raise
    except Exception as exc:
        if "1168" in str(exc):
            return
        raise OrderAuthorizationKeyError("authorization Key could not be deleted") from exc
