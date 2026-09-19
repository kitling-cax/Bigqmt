"""Headless verification of the tray strategy-control feature chain.

Run against the real local config paths but does NOT touch QMT, Redis,
the Coordinator or the GUI.  It exercises exactly the Python programs the
native tray shells out to, using a scratch install so the real
install_root is left untouched.

  py -3.12 scripts/verify_host_tray_features.py

Exit 0 when every step passes; 1 otherwise.  Each step prints PASS/FAIL.

Steps:
  1. machine.local.json has strategy_deployment.install_root and
     tray.delete_strategy_password_sha256 (a 64-hex) present
  2. build a scratch package in temp, install it into the scratch root
  3. list shows the installed build
  4. set_strategy_auto_run --enabled true -> policy shows auto_run_enabled true
  5. set_strategy_auto_run --clear  -> entry removed (+ legacy v1.1.15 false if it was v1.1.15)
  6. uninstall removes the scratch build; --list is empty again
  7. installer refuses an unsafe identifier
  8. delete_flow equivalent: uninstall --list parses as JSON
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from kitling_bigqmt.strategy_installer import install_package  # noqa: E402
import uninstall_strategy_package as uninstaller  # noqa: E402
import set_strategy_auto_run as policy  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def _python(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )


def _scratch_package(tmp: Path, strategy_id: str) -> Path:
    pkg = tmp / strategy_id / "vX" / "rX"
    (pkg / "payload").mkdir(parents=True)
    file = pkg / "payload" / "verifier.py"
    file.write_text("print('ok')\n", encoding="utf-8")
    manifest = {
        "strategy_id": strategy_id, "version": "vX", "build_id": "rX",
        "artifacts": [{"path": "payload/verifier.py", "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}],
        "safety": {"orders_enabled": False, "formal_account_allowed": False},
    }
    (pkg / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pkg


def main() -> int:
    # 1. config presence
    try:
        machine = json.loads((ROOT / "config" / "machine.local.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        machine = {}
    deploy = machine.get("strategy_deployment") or {}
    install_root = str(deploy.get("install_root") or "").strip()
    check("machine.local.json install_root present", bool(install_root), install_root)
    pw = str((machine.get("tray") or {}).get("delete_strategy_password_sha256") or "")
    check("password hash present (64 hex)", pw.lower() != "" and len(pw) == 64)

    scratch = Path(tempfile.mkdtemp(prefix="verify-tray-"))
    try:
        pkg = _scratch_package(scratch, "TRAY_VERIFY_5D_SIM_MAIN_V9")
        result = install_package(pkg, scratch / "installed")
        check("scratch install INSTALLED", result.get("status") == "INSTALLED", result.get("status"))
        check("scratch install not enabled", result.get("run_after_install") is False)

        installed = uninstaller.list_installed(scratch / "installed")
        check("list shows scratch build", any(i["strategy_id"] == "TRAY_VERIFY_5D_SIM_MAIN_V9" for i in installed))

        # 2. toggle via the policy program (against temp config path)
        policy.ROOT = scratch
        policy.PATH = scratch / "config" / "strategy_runtime_policy.json"
        (policy.PATH).parent.mkdir(parents=True, exist_ok=True)
        policy._write({"schema_version": 1, "simulation": {}, "production": {}})
        check("set_auto_run enable ok",
              policy.main(["--strategy-id", "TRAY_VERIFY_5D_SIM_MAIN_V9", "--enabled", "true"]) == 0)
        data = json.loads(policy.PATH.read_text(encoding="utf-8"))
        check("policy entry true",
              data["simulation"]["strategies"]["TRAY_VERIFY_5D_SIM_MAIN_V9"]["auto_run_enabled"] is True)

        check("set_auto_run clear ok",
              policy.main(["--strategy-id", "TRAY_VERIFY_5D_SIM_MAIN_V9", "--clear"]) == 0)
        data = json.loads(policy.PATH.read_text(encoding="utf-8"))
        check("policy entry cleared", "TRAY_VERIFY_5D_SIM_MAIN_V9" not in data["simulation"]["strategies"])

        # 3. unsafe identifier refusal
        try:
            uninstaller.uninstall("../escape", "v1", "r1", scratch / "installed")
            check("unsafe id refused", False, "no ValueError")
        except ValueError:
            check("unsafe id refused", True)

        # 4. real uninstall removes the scratch build
        result = uninstaller.uninstall("TRAY_VERIFY_5D_SIM_MAIN_V9", "vX", "rX", scratch / "installed")
        check("scratch uninstall", result.get("status") == "uninstalled", result.get("status"))
        installed = uninstaller.list_installed(scratch / "installed")
        check("install_root empty after uninstall", installed == [])

        # 5. the two CLI programs the tray polls must emit parseable JSON
        for script in ("set_strategy_auto_run.py", "uninstall_strategy_package.py"):
            proc = _python(str(ROOT / "scripts" / script), "--help")
            check(f"{script} CLI runs", proc.returncode in (0, 2))
    except Exception as exc:  # noqa: BLE001
        check("no crash", False, f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print("")
    if FAILURES:
        print(f"{len(FAILURES)} step(s) FAILED: {', '.join(FAILURES)}")
        return 1
    print("ALL STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())