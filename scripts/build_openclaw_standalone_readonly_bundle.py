"""Build a self-contained Python 3.11+ observer-only OpenClaw candidate."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.3-readonly"
FILES = {
    "openclaw/bigqmt-operator/SKILL.md": "skill/SKILL.md",
    "openclaw/bigqmt-operator/standalone/bigqmt_readonly_mcp.py": "mcp/bigqmt_readonly_mcp.py",
    "openclaw/bigqmt-operator/standalone/bigqmt_readonly.local.example.json": "mcp/bigqmt_readonly.local.example.json",
    "openclaw/bigqmt-operator/standalone/server.example.windows.json": "mcp/server.example.windows.json",
    "openclaw/bigqmt-operator/standalone/server.example.linux.json": "mcp/server.example.linux.json",
}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError("immutable release already exists")
    destination.mkdir(parents=True)
    entries = []
    for source_rel, target_rel in FILES.items():
        target = destination / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source_rel, target)
        entries.append({"path": target_rel, "sha256": _hash(target), "bytes": target.stat().st_size})
    readme = destination / "README_INSTALL.md"
    # Write fixed UTF-8/LF bytes.  Using text-mode output on Windows creates
    # CRLF and makes a Linux-normalized local copy fail the immutable checksum.
    readme.write_bytes(("# BigQMT OpenClaw Standalone Observer\n\n"
                        "Python 3.11+ only; no BigQMT checkout, QMT terminal, Redis, token or order capability is required. "
                        "Copy this release locally, verify checksums, copy the example endpoint file to bigqmt_readonly.local.json, "
                        "then use the OS-specific MCP server template.\n").encode("utf-8"))
    entries.append({"path": "README_INSTALL.md", "sha256": _hash(readme), "bytes": readme.stat().st_size})
    manifest = {"schema_version": 1, "release": "openclaw-bigqmt-bundle-" + VERSION,
                "channel": "candidate", "scope": "observer_readonly", "orders_enabled": False,
                "requires": {"python": ">=3.11", "bigqmt_project": False}, "files": entries}
    # Metadata is also part of the release integrity boundary.  Write raw LF
    # bytes, never platform text-mode output, so Windows and Linux hash the
    # same manifest/checksum files.
    (destination / "manifest.json").write_bytes(
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    (destination / "checksums.sha256").write_bytes(
        ("\n".join("%s  %s" % (item["sha256"], item["path"]) for item in entries) + "\n").encode("utf-8")
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(ROOT / "dist" / ("openclaw-bigqmt-bundle-" + VERSION)), ensure_ascii=False, indent=2))
