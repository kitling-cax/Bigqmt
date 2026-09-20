"""Set the local tray deletion-password hash without storing plaintext.

The password is accepted from an interactive masked prompt or the short-lived
child-process environment used by the native tray.  Only its SHA-256 hash is
written to config/machine.local.json; neither JSON output nor logs contain the
password or the hash.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MACHINE_LOCAL = ROOT / "config" / "machine.local.json"
MINIMUM_PASSWORD_LENGTH = 8


def _password_from_input() -> str:
    value = os.environ.pop("BIGQMT_TRAY_DELETE_PASSWORD_INPUT", "")
    if value:
        return value
    first = getpass.getpass("Tray delete password: ")
    second = getpass.getpass("Confirm tray delete password: ")
    if first != second:
        raise ValueError("delete password confirmation does not match")
    return first


def _load_machine_local(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"schema_version": 1}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("machine.local.json must contain a JSON object")
    return value


def set_delete_password(path: Path, password: str) -> None:
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError("delete password must contain at least 8 characters")
    value = _load_machine_local(path)
    tray = value.get("tray")
    if not isinstance(tray, dict):
        tray = {}
        value["tray"] = tray
    tray["delete_strategy_password_sha256"] = hashlib.sha256(password.encode("utf-8")).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Set the local BigQMT tray deletion password")
    parser.add_argument("action", choices=("set",))
    args = parser.parse_args()
    try:
        if args.action == "set":
            set_delete_password(MACHINE_LOCAL, _password_from_input())
        print(json.dumps({"configured": True, "secret_logged": False}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"configured": False, "error": str(exc), "secret_logged": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
