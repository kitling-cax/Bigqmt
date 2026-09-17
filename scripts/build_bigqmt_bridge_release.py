"""Build reproducible simulation and production-readonly QMT upload ZIPs."""

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path


RELEASE_ID = "kitling-bigqmt-bridge-20260909-rc3"
ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "staging" / "qmt_bridge_simulation"
DIST = ROOT / "dist" / RELEASE_ID

COMMON_FILES = (
    "BIGQMT_REDIS_DRYRUN.py",
    "bigqmt_signal_trader_strategy.py",
    "bigqmt_signal_trader_redis_rpc_runtime.py",
)

PROFILES = {
    "SIMULATION": {
        "profile": ROOT / "deploy" / "profiles" / "simulation" / "bigqmt_signal_trader_local_config.py",
        "expected_qmt_python_dir": r"C:\BigQMT\work\国金QMT交易端模拟\python",
        "redis_port": 6379,
        "redis_db": 5,
        "host_configs": (
            ROOT / "config" / "redis" / "redis-simulation.conf",
            ROOT / "config" / "host_gateway.simulation.json",
        ),
    },
    "PRODUCTION_CAPABLE_LOCKED": {
        "profile": ROOT / "deploy" / "profiles" / "production_readonly" / "bigqmt_signal_trader_local_config.py",
        "expected_qmt_python_dir": r"C:\BigQMT\work\国金证券QMT交易端\python",
        "redis_port": 6380,
        "redis_db": 5,
        "host_configs": (
            ROOT / "config" / "redis" / "redis-production.conf",
            ROOT / "config" / "host_gateway.production_readonly.json",
        ),
    },
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_deployment_readme(package_root, profile_name, profile):
    is_simulation = profile_name == "SIMULATION"
    account_hint = "9902****2040" if is_simulation else "8890****6688"
    next_step = (
        "Run the SIMULATION package first. Stop BIGQMT_REDIS_DRYRUN before "
        "starting BIGQMT_BRIDGE in the same terminal."
        if is_simulation else
        "Start the isolated production Redis on 127.0.0.1:6380 first, then "
        "run this package only after the simulation Bridge has passed its read-only regression."
    )
    content = """BIGQMT_BRIDGE RC3 deployment candidate
=======================================

Environment: {environment}
Expected QMT Python directory: {python_dir}
Bound local account: {account}
Redis: 127.0.0.1:{port}, DB {db}

This is the same complete Bridge code used in both environments. It contains
the future order/cancel implementation, but this package starts with every
execution route hard-locked: rpc_allow_order_methods=False, orders_enabled=False,
execution_consumer_enabled=False, preflight/parity BLOCKED, and fresh Tray
runtime-control evidence required. Account binding is a fail-closed identity
check, never an order authorization.

Install:

  1. Back up existing QMT Python Bridge files (or keep this ZIP as rollback).
  2. Copy qmt_python contents into the exact QMT python directory above.
  3. In that QMT terminal create BIGQMT_BRIDGE and paste qmt_editor\\BIGQMT_BRIDGE.py.
  4. Run on minute bars. Check the strategy log for release rc3 and the bound account.
  5. Verify only ping, account, positions, orders, trades and quote reads.

{next_step}

Do not run BIGQMT_REDIS_DRYRUN and BIGQMT_BRIDGE together in one terminal:
they share the environment Redis request channel. Do not enable any order
switch to troubleshoot an identity, Redis or quote problem. Formal execution
has no current approval and cannot be enabled by changing this QMT strategy.
""".format(
        environment=profile_name,
        python_dir=profile["expected_qmt_python_dir"],
        account=account_hint,
        port=profile["redis_port"],
        db=profile["redis_db"],
        next_step=next_step,
    )
    (package_root / "README.txt").write_text(content, encoding="utf-8")


def copy_required(profile_name, profile):
    package_root = DIST / ("BIGQMT_BRIDGE_" + profile_name)
    qmt_python = package_root / "qmt_python"
    qmt_editor = package_root / "qmt_editor"
    host_config = package_root / "host_config"
    qmt_python.mkdir(parents=True)
    qmt_editor.mkdir()
    host_config.mkdir()

    for name in COMMON_FILES:
        shutil.copy2(str(STAGING / name), str(qmt_python / name))
    shutil.copytree(
        str(STAGING / "bigqmt_signal_trader"),
        str(qmt_python / "bigqmt_signal_trader"),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copy2(str(profile["profile"]), str(qmt_python / "bigqmt_signal_trader_local_config.py"))
    shutil.copy2(str(STAGING / "BIGQMT_BRIDGE.py"), str(qmt_editor / "BIGQMT_BRIDGE.py"))
    write_deployment_readme(package_root, profile_name, profile)
    for source in profile["host_configs"]:
        shutil.copy2(str(source), str(host_config / source.name))

    files = []
    for path in sorted(item for item in package_root.rglob("*") if item.is_file()):
        files.append({
            "path": path.relative_to(package_root).as_posix(),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        })
    manifest = {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "environment": profile_name,
        "expected_qmt_python_dir": profile["expected_qmt_python_dir"],
        "redis": {"host": "127.0.0.1", "port": profile["redis_port"], "db": profile["redis_db"]},
        "orders_enabled": False,
        "rpc_allow_order_methods": False,
        "formula_server_client_enabled": profile_name == "SIMULATION",
        "files": files,
    }
    manifest_path = package_root / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    zip_path = DIST / (package_root.name + ".zip")
    with zipfile.ZipFile(str(zip_path), "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in package_root.rglob("*") if item.is_file()):
            archive.write(str(path), arcname=(package_root.name + "/" + path.relative_to(package_root).as_posix()))
    return package_root, zip_path


def main():
    if DIST.exists():
        raise SystemExit("release directory already exists; refusing to overwrite: %s" % DIST)
    DIST.mkdir(parents=True)
    outputs = []
    for profile_name, profile in PROFILES.items():
        outputs.append(copy_required(profile_name, profile))
    for package_root, zip_path in outputs:
        print("built %s" % package_root)
        print("zip   %s sha256=%s" % (zip_path, sha256(zip_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
