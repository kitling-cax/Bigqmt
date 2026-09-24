"""Manage one account's local order-authorization Key.

Plaintext is accepted only from an interactive masked prompt or the short-lived
BIGQMT_ORDER_AUTHORIZATION_KEY_INPUT child-process environment variable.  JSON
output never contains the Key.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.order_authorization_key import (  # noqa: E402
    OrderAuthorizationKeyError,
    delete,
    status,
    write,
)


def _account(profile: str, supplied: str) -> str:
    value = str(supplied or "").strip()
    if value:
        return value
    return str(load_gateway(ROOT, profile).get("account_id") or "").strip()


def _secret_from_input() -> str:
    value = os.environ.pop("BIGQMT_ORDER_AUTHORIZATION_KEY_INPUT", "")
    if value:
        return value
    first = getpass.getpass("Order authorization Key: ")
    second = getpass.getpass("Confirm Key: ")
    if first != second:
        raise OrderAuthorizationKeyError("authorization Key confirmation does not match")
    return first


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage local BigQMT order-authorization Key")
    parser.add_argument("action", choices=("status", "set", "delete"))
    parser.add_argument("--profile", required=True, choices=("simulation", "production_readonly"))
    parser.add_argument("--account", default="")
    args = parser.parse_args()
    account_id = _account(args.profile, args.account)
    try:
        if args.action == "set":
            result = write(args.profile, account_id, _secret_from_input())
        elif args.action == "delete":
            delete(args.profile)
            result = status(args.profile, account_id)
        else:
            result = status(args.profile, account_id)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, OrderAuthorizationKeyError) as exc:
        print(json.dumps({
            "profile": args.profile,
            "account_id": account_id,
            "installed": False,
            "valid": False,
            "state": "ERROR",
            "error": str(exc),
            "orders_enabled": False,
        }, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
