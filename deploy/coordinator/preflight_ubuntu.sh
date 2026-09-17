#!/usr/bin/env bash
set -euo pipefail

fail() { echo "PREFLIGHT_FAIL: $1" >&2; exit 1; }
command -v python3 >/dev/null || fail "python3 missing"
python3 -c 'import sys; assert sys.version_info >= (3,10), sys.version'
command -v systemctl >/dev/null || fail "systemd missing"
test "$(id -u)" -eq 0 || fail "run as root"
test -d /opt || fail "/opt missing"
test "$(df -Pk /var/lib | awk 'NR==2 {print $4}')" -gt 1048576 || fail "less than 1GiB free on /var/lib"
if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(:|\])18443$'; then
  fail "TCP 18443 already listening"
fi
echo "PREFLIGHT_OK python=$(python3 --version 2>&1)";
