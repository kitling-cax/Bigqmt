"""Copy one validated private NAS config into the local machine cache.

Run explicitly during installation or a controlled configuration update. The
runtime never reads the NAS path automatically, so a share outage cannot stop
the tray from starting with the last known-good local config.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.machine_config import _deep_merge, load_private_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="NAS private machine.json")
    parser.add_argument("--root", type=Path, required=True, help="local BigQMT project root")
    parser.add_argument("--host-id", required=True)
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    payload = load_private_config(source)
    coordinator = payload.get("coordinator") or {}
    if str(coordinator.get("host_id") or "") != args.host_id:
        raise SystemExit("private config host_id does not match the target host")

    output = args.root / "config" / "machine.local.json"
    existing = {}
    if output.is_file():
        try:
            existing = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit("existing local machine.local.json is invalid") from exc
        if not isinstance(existing, dict):
            raise SystemExit("existing local machine.local.json must be an object")

    merged = _deep_merge(payload, existing)
    merged["private_config"] = {
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
        "runtime_reads_nas": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"output": str(output), "source_sha256": merged["private_config"]["source_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
