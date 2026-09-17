#!/usr/bin/env python3
"""Container-local readiness probe; it never sends a state-changing request."""
from __future__ import annotations

import json
import os
from urllib.request import urlopen

port = int(os.environ.get("BIGQMT_COORDINATOR_PORT", "18443"))
with urlopen(f"http://127.0.0.1:{port}/readyz", timeout=3) as response:
    payload = json.loads(response.read().decode("utf-8"))
if response.status != 200 or payload.get("status") != "ready" or payload.get("mode") != "shadow_readonly":
    raise SystemExit(1)
