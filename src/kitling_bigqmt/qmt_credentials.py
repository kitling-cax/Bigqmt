"""Windows Credential Manager storage for QMT login secrets.

Only generic credentials are used.  No caller receives a serialised secret,
and callers should never include returned values in logs or JSON responses.
"""

from __future__ import annotations

from typing import Any


class QmtCredentialError(RuntimeError):
    """Credential Manager is unavailable or rejected an operation."""


def target_name(profile: str) -> str:
    if profile not in {"simulation", "production_readonly"}:
        raise QmtCredentialError("unsupported profile")
    return "KitlingBigQMT/QmtLogin/" + profile


def is_available(profile: str) -> bool:
    try:
        read(profile)
        return True
    except QmtCredentialError:
        return False


def read(profile: str) -> dict[str, str]:
    """Read a credential pair, raising without disclosing values on failure."""
    try:
        import win32cred

        item: dict[str, Any] = win32cred.CredRead(target_name(profile), win32cred.CRED_TYPE_GENERIC)
        username = str(item.get("UserName") or "")
        blob = item.get("CredentialBlob") or b""
        password = blob.decode("utf-16-le") if isinstance(blob, bytes) else str(blob)
        if not username or not password:
            raise QmtCredentialError("credential is incomplete")
        return {"user": username, "password": password}
    except QmtCredentialError:
        raise
    except Exception as exc:
        raise QmtCredentialError("credential is unavailable") from exc


def write(profile: str, username: str, password: str) -> None:
    if not str(username).strip() or not str(password):
        raise QmtCredentialError("username and password are required")
    try:
        import win32cred

        win32cred.CredWrite({
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": target_name(profile),
            "UserName": str(username).strip(),
            # pywin32's CredWrite binding expects a Unicode string here and
            # marshals it to the Windows credential blob itself.  Passing
            # bytes causes ``TypeError: bytes cannot be converted to
            # Unicode`` before the credential store is ever reached.
            "CredentialBlob": str(password),
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
            "Comment": "BigQMT local terminal login; never stored in project files.",
        }, 0)
    except Exception as exc:
        raise QmtCredentialError("credential could not be saved") from exc


def delete(profile: str) -> None:
    try:
        import win32cred

        win32cred.CredDelete(target_name(profile), win32cred.CRED_TYPE_GENERIC, 0)
    except Exception as exc:
        # Delete is deliberately idempotent from an operator perspective.
        if "1168" in str(exc):
            return
        raise QmtCredentialError("credential could not be deleted") from exc
