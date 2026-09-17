"""Fail closed when a public BigQMT source snapshot contains credentials."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATH = re.compile(
    r"(^|/)(?:secrets?|credentials?|runtime_data|logs)(?:/|$)|"
    r"(?:machine\.local\.json|.*\.key|.*\.pem|.*\.pfx|.*\.secret(?:\.json)?)$",
    re.IGNORECASE,
)
SECRET = re.compile(
    r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[0-9A-Z]{16}|-----BEGIN [^-]+ PRIVATE KEY-----|"
    r"(?:redis[_-]?password|qmt[_-]?password|api[_-]?key|access[_-]?token|"
    r"bearer[_-]?token|secret[_-]?b64)\s*[:=]\s*['\"][^'\"]{12,}['\"]|"
    r"(?<!approval_)(?:password|passwd)\s*=\s*['\"][^'\"]{12,}['\"])",
    re.IGNORECASE,
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, stdout=subprocess.PIPE
    )
    return [item for item in result.stdout.decode().split("\0") if item]


def main() -> int:
    errors: list[str] = []
    files = tracked_files()
    for relative in files:
        if FORBIDDEN_PATH.search(relative.replace("\\", "/")):
            errors.append(f"forbidden tracked path: {relative}")
            continue
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if SECRET.search(text):
            errors.append(f"credential-like literal: {relative}")
    if errors:
        print("Public safety check failed:")
        print("\n".join(f"- {item}" for item in errors))
        return 1
    print(f"Public safety check passed: {len(files)} tracked files scanned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
