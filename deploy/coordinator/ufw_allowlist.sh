#!/usr/bin/env bash
set -euo pipefail

# Run on 192.0.2.121 as root after confirming the host's existing policy.
# The first rule admits only the development Host Agent. Add the other two
# sources deliberately when their read-only agents are ready.
command -v ufw >/dev/null || { echo 'ufw is required' >&2; exit 1; }
ufw default deny incoming
ufw allow from 192.0.2.105 to any port 18443 proto tcp comment 'BigQMT dev host agent'
# ufw allow from 192.0.2.125 to any port 18443 proto tcp comment 'BigQMT future host'
# ufw allow from 198.51.100.113 to any port 18443 proto tcp comment 'BigQMT standby host'
ufw allow ssh
ufw --force enable
ufw status numbered
