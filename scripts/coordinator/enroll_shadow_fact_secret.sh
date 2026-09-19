#!/usr/bin/env bash
# Register one Host Agent HMAC fact Secret with the .121 Shadow Coordinator.
#
# The source Secret is already staged on the Coordinator host by the matching
# PowerShell client.  This script prints only key IDs and host IDs; it never
# prints secret_b64 or copies a secret into the repository/NAS.
set -euo pipefail

STAGED_FILE="${1:-}"
TRUSTED_FILE="${2:-/etc/kitling-bigqmt-coordinator-shadow/fact-identities.json}"
CONTAINER_NAME="${3:-kitling-bigqmt-coordinator-shadow}"

if [[ -z "$STAGED_FILE" || ! -f "$STAGED_FILE" ]]; then
  echo "ERROR: staged Secret file does not exist" >&2
  exit 2
fi

if [[ "$TRUSTED_FILE" != "/etc/kitling-bigqmt-coordinator-shadow/fact-identities.json" ]]; then
  echo "ERROR: unexpected trusted-hosts destination" >&2
  exit 2
fi

sudo python3 - "$STAGED_FILE" "$TRUSTED_FILE" <<'PY'
import base64
import json
import os
import shutil
import stat
import sys
import time

staged_path, trusted_path = sys.argv[1:3]
placeholder_prefixes = ("192.0.2.", "198.51.100.")


def load_document(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    if document.get("schema_version") != 1 or not isinstance(document.get("hosts"), list):
        raise SystemExit("ERROR: invalid fact identity document")
    return document


def validate(entry: object) -> dict:
    if not isinstance(entry, dict):
        raise SystemExit("ERROR: invalid fact identity entry")
    host_id = str(entry.get("host_id") or "").strip()
    key_id = str(entry.get("key_id") or "").strip()
    status = str(entry.get("status") or "ACTIVE").upper()
    if not host_id or not key_id or status not in {"ACTIVE", "NEXT"}:
        raise SystemExit("ERROR: invalid fact identity metadata")
    if host_id.startswith(placeholder_prefixes):
        raise SystemExit("ERROR: placeholder host_id rejected")
    try:
        secret = base64.b64decode(str(entry.get("secret_b64") or ""), validate=True)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("ERROR: invalid fact Secret encoding") from exc
    if len(secret) < 32:
        raise SystemExit("ERROR: fact Secret is shorter than 32 bytes")
    return {
        "host_id": host_id,
        "key_id": key_id,
        "status": status,
        "secret_b64": str(entry["secret_b64"]),
    }


staged = load_document(staged_path)
incoming = [validate(item) for item in staged["hosts"]]
if len(incoming) != 1:
    raise SystemExit("ERROR: exactly one Host Agent identity is required per enrollment")

trusted = load_document(trusted_path)
merged = {str(item.get("key_id") or ""): item for item in trusted["hosts"]}
entry = incoming[0]
previous = merged.get(entry["key_id"])
if previous and str(previous.get("host_id") or "").strip() != entry["host_id"]:
    raise SystemExit("ERROR: key_id is already assigned to a different host_id")
merged[entry["key_id"]] = entry

metadata_before = os.stat(trusted_path)
backup = f"{trusted_path}.bak.{time.strftime('%Y%m%d_%H%M%S')}"
shutil.copy2(trusted_path, backup)
payload = {
    "schema_version": 1,
    "hosts": [merged[key] for key in sorted(merged)],
}

# Preserve the bind-mount inode, ownership and permissions.  The service
# reloads this file for every facts-only POST, so a restart is unnecessary.
with open(trusted_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
os.chmod(trusted_path, stat.S_IMODE(metadata_before.st_mode))
os.chown(trusted_path, metadata_before.st_uid, metadata_before.st_gid)

print(json.dumps({
    "status": "ENROLLED",
    "host_id": entry["host_id"],
    "key_id": entry["key_id"],
    "trusted_key_ids": sorted(merged),
    "backup": backup,
}, ensure_ascii=False))
PY

# A copied HMAC Secret is a one-use staging artifact.  Remove it only after a
# successful merge, leaving the source file on the host unchanged.
rm -f -- "$STAGED_FILE"

if ! sudo docker inspect --format '{{.State.Health.Status}}' "$CONTAINER_NAME" | grep -qx healthy; then
  echo "ERROR: Shadow Coordinator is not healthy after enrollment" >&2
  exit 3
fi

sudo docker exec -i "$CONTAINER_NAME" python3 - <<'PY'
import json
document = json.load(open("/secrets/fact-identities.json", encoding="utf-8"))
print(json.dumps({
    "container_trusted_hosts": [
        {"host_id": item.get("host_id"), "key_id": item.get("key_id"), "status": item.get("status")}
        for item in document.get("hosts", [])
    ]
}, ensure_ascii=False))
PY
