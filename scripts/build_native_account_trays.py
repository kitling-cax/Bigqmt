"""Build transparent one-account native tray releases (one EXE per folder)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ("bigqmt_tray_simulation.py", "BigQMT_模拟盘", "BigQMT_Simulation.ico"),
    ("bigqmt_tray_production_readonly.py", "BigQMT_正式只读", "BigQMT_Production_ReadOnly.ico"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyinstaller-path", type=Path, default=None,
                        help="optional local directory containing the PyInstaller module")
    args = parser.parse_args()
    environment = None
    if args.pyinstaller_path:
        environment = dict(__import__("os").environ)
        existing = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = str(args.pyinstaller_path.resolve()) + (";" + existing if existing else "")
    for source, name, icon_name in TARGETS:
        command = [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--noconsole",
            "--name", name, "--distpath", str(ROOT / "tray"),
            "--workpath", str(ROOT / "runtime_data" / "_build" / "native_trays" / name),
            "--specpath", str(ROOT / "runtime_data" / "_build" / "native_trays" / "spec"),
            "--paths", str(ROOT / "src"), "--hidden-import", "win32timezone",
            "--icon", str(ROOT / "tray" / icon_name),
            str(ROOT / "scripts" / source),
        ]
        completed = subprocess.run(command, cwd=str(ROOT), env=environment, check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
