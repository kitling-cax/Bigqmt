"""Validate or explicitly publish the latest isolated BigQMT Raw overlay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.raw_overlay_publisher import (  # noqa: E402
    APPROVAL_TOKEN, RawOverlayPublishError, publish_isolated_raw, validate_candidate,
)


def latest_release() -> Path:
    candidates = sorted((p for p in (ROOT / "runtime_data" / "candidates").glob("bigqmt_candidate_*") if p.is_dir()), key=lambda p: p.name)
    if not candidates:
        raise FileNotFoundError("no candidate release")
    return candidates[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate/publish isolated BigQMT Raw overlay")
    parser.add_argument("release_dir", nargs="?", type=Path)
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    parser.add_argument("--approve-raw-publish", action="store_true", help="perform isolated Raw copy-on-write publish")
    args = parser.parse_args()
    release = (args.release_dir or latest_release()).resolve()
    try:
        checked = validate_candidate(release)
        if not args.approve_raw_publish:
            print(json.dumps({"status": "READY_FOR_EXPLICIT_RAW_PUBLISH", "approval_required": True,
                              "approval_token_name": APPROVAL_TOKEN, "validation": checked,
                              "lake_write": False, "latest_modified": False}, ensure_ascii=False, indent=2))
            return 0
        result = publish_isolated_raw(release, args.lake_root, APPROVAL_TOKEN)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RawOverlayPublishError, PermissionError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": "%s: %s" % (type(exc).__name__, exc),
                          "lake_write": False, "latest_modified": False}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
