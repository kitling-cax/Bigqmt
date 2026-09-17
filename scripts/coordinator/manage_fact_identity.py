"""Generate/rotate Host Agent fact identities in a protected local file.

This utility is intentionally not run by the project build. The output path
must be a service/container Secret location outside the repository and NAS
release tree. It prints only the key ID, never the secret.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.host_fact_identity import credential_document, generate_credential  # noqa: E402


def _write(path: Path, document: dict) -> None:
    if path.resolve().is_relative_to(ROOT.resolve()):
        raise SystemExit("refusing to write a fact Secret inside the project tree")
    if path.exists():
        raise SystemExit("refusing to overwrite an existing Secret; use a new rotation path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--key-id")
    args = parser.parse_args()
    credential = generate_credential(args.host_id, key_id=args.key_id)
    _write(args.output, credential_document([credential]))
    print(json.dumps({"status": "GENERATED", "host_id": credential.host_id, "key_id": credential.key_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
