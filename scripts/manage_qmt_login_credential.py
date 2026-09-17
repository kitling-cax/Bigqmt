"""Create, inspect or remove a profile-local QMT login credential.

Run interactively in a trusted local terminal.  Password input uses getpass,
is never echoed, never printed and never written into the project directory.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.qmt_credentials import (  # noqa: E402
    QmtCredentialError,
    delete,
    is_available,
    write,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("set", "status", "delete"))
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), required=True)
    parser.add_argument("--user", default=None, help="QMT login user; omit to enter interactively")
    args = parser.parse_args()
    try:
        if args.action == "status":
            print(json.dumps({"profile": args.profile, "credential_available": is_available(args.profile)}, ensure_ascii=False))
            return 0
        if args.action == "delete":
            delete(args.profile)
            print(json.dumps({"profile": args.profile, "deleted": True}, ensure_ascii=False))
            return 0
        user = args.user or input("QMT login user: ").strip()
        password = getpass.getpass("QMT login password: ")
        verify = getpass.getpass("Confirm password: ")
        if password != verify:
            raise QmtCredentialError("password confirmation does not match")
        write(args.profile, user, password)
        print(json.dumps({"profile": args.profile, "credential_saved": True}, ensure_ascii=False))
        return 0
    except QmtCredentialError as exc:
        print(json.dumps({"profile": args.profile, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
