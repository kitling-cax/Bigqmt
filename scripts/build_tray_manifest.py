"""Build a portable, non-secret manifest for the BigQMT Tray release."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAY_FILES = (
    "tray/BigQMTTray.ps1",
    "tray/launch_simulation_tray.cmd",
    "tray/launch_production_readonly_tray.cmd",
    "tray/BigQMT_Simulation.exe",
    "tray/BigQMT_Production_ReadOnly.exe",
    "tray/BigQMT_Simulation.ico",
    "tray/BigQMT_Production_ReadOnly.ico",
    "tray/BigQMT_native_tray_checksums.sha256",
    "config/tray_profiles.json",
    "scripts/bigqmt_runtime.py",
    "scripts/qmt_launcher_cli.py",
    "scripts/miniqmt_launcher_cli.py",
    "scripts/check_tray_health.py",
    "scripts/diagnose_tray.py",
    "scripts/check_portable_deployment.py",
    "scripts/build_native_account_trays.ps1",
    "scripts/create_local_backup.py",
    "src/kitling_bigqmt/runtime_control.py",
    "src/kitling_bigqmt/tray_health.py",
    "src/kitling_bigqmt/tray_diagnostics.py",
    "src/kitling_bigqmt/portable_deployment.py",
    "src/kitling_bigqmt/local_backup.py",
)
GENERATED_TRAY_FILES = {
    "tray/BigQMT_Simulation.exe",
    "tray/BigQMT_Production_ReadOnly.exe",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(output: Path, release_id: str, *, strict: bool = True) -> dict:
    """Build a release manifest.

    A real release is strict and must include the two compiled native Tray
    executables. Source-only CI intentionally uses ``strict=False`` so it
    validates the manifest contract without committing generated binaries.
    """
    files = []
    missing_files = []
    for relative in TRAY_FILES:
        if not strict and relative in GENERATED_TRAY_FILES:
            missing_files.append(relative)
            continue
        path = ROOT / relative
        if not path.is_file():
            if strict:
                raise FileNotFoundError(relative)
            missing_files.append(relative)
            continue
        files.append({"path": relative, "sha256": sha256(path), "bytes": path.stat().st_size})
    manifest = {
        "schema_version": 1,
        "release_id": release_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "BIGQMT_TRAY_READ_ONLY_OPERATOR",
        "profiles": ["simulation", "production_readonly"],
        "orders_enabled": False,
        "execution_consumer_enabled": False,
        "auto_login_secrets_embedded": False,
        "supports_windows_credential_auto_login": True,
        "supports_miniqmt_linkmini_passwordless": True,
        "missing_files": missing_files,
        "files": files,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-id", default="kitling-bigqmt-tray-20260909-rc1")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "kitling-bigqmt-tray-20260909-rc1" / "manifest.json")
    args = parser.parse_args()
    manifest = build(args.output, args.release_id)
    print(json.dumps({"output": str(args.output), "release_id": manifest["release_id"], "file_count": len(manifest["files"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
