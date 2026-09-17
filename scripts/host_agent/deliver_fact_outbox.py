"""Deliver signed local facts to the Shadow Coordinator and ACK only safe IDs.

The command is intentionally facts-only.  It refuses non-Shadow port 18666
unless ``--allow-non-shadow`` is explicitly supplied, and it has no order,
lease, QMT or Redis code path.  Any transport or acknowledgement error leaves
the local Outbox rows pending for a later retry.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.coordinator_outbox import LocalOutbox  # noqa: E402
from kitling_bigqmt.host_fact_identity import load_credentials  # noqa: E402
from kitling_bigqmt.host_fact_uploader import acknowledge_fact_batch, build_pending_envelope  # noqa: E402


def _post_json(endpoint: str, envelope: dict, timeout: float) -> tuple[int, dict]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            body = {"status": "HTTP_ERROR", "error": str(exc.code)}
        return int(exc.code), body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=("simulation", "production_readonly"))
    parser.add_argument("--secret-file", type=Path, required=True)
    parser.add_argument("--outbox-path", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--allow-non-shadow", action="store_true", help="explicitly permit a non-18666 endpoint")
    args = parser.parse_args(argv)
    if ":18666/" not in args.endpoint and not args.allow_non_shadow:
        print(json.dumps({"status": "REFUSED_NON_SHADOW_ENDPOINT", "orders_enabled": False}, ensure_ascii=False))
        return 2
    credentials = load_credentials(args.secret_file)
    if len(credentials) != 1:
        raise SystemExit("exactly one active fact identity is required for this Host Agent")
    outbox = LocalOutbox(args.outbox_path)
    envelope, event_ids = build_pending_envelope(outbox, credentials[0], ttl_seconds=60)
    if envelope is None:
        print(json.dumps({"status": "EMPTY", "pending": 0, "orders_enabled": False}, ensure_ascii=False))
        return 0
    try:
        http_status, response = _post_json(args.endpoint, envelope, args.timeout)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        outbox.record_delivery_failure(event_ids, type(exc).__name__)
        print(json.dumps({"status": "RETRY_PENDING", "error": type(exc).__name__, "pending": len(outbox.pending()), "orders_enabled": False}, ensure_ascii=False))
        return 1
    if http_status not in (200, 202):
        outbox.record_delivery_failure(event_ids, str(response.get("status") or "HTTP_" + str(http_status)))
        print(json.dumps({"status": "RETRY_PENDING", "http_status": http_status, "response_status": response.get("status"), "pending": len(outbox.pending()), "orders_enabled": False}, ensure_ascii=False))
        return 1
    try:
        acknowledged = acknowledge_fact_batch(outbox, event_ids, response)
    except Exception as exc:
        outbox.record_delivery_failure(event_ids, type(exc).__name__)
        print(json.dumps({"status": "RETRY_PENDING", "error": type(exc).__name__, "pending": len(outbox.pending()), "orders_enabled": False}, ensure_ascii=False))
        return 1
    pending_after = len(outbox.pending())
    print(json.dumps({"status": response.get("status"), "http_status": http_status, "acknowledged": acknowledged, "pending": pending_after, "orders_enabled": False, "facts_only": response.get("facts_only")}, ensure_ascii=False))
    return 0 if response.get("status") in {"ACCEPTED", "REPLAYED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
