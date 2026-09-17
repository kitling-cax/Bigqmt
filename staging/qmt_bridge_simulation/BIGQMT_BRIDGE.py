#coding:gbk
"""Simulation BigQMT bridge strategy entry.

Paste this ASCII-only entry into a new QMT Python strategy named
BIGQMT_BRIDGE.  It deliberately reuses the verified local loader and calls
the same QMT callback bindings as BIGQMT_REDIS_DRYRUN.  The local config keeps
order/cancel RPC disabled by default; the bridge only gains write capability
after every execution_admission gate is explicitly released.
"""
import os
import sys

BIGQMT_BRIDGE_RELEASE_ID = "kitling-bigqmt-bridge-20260909-rc3"
print("[bigqmt_bridge] release=%s" % BIGQMT_BRIDGE_RELEASE_ID)


def _qmt_python_dir():
    for item in sys.path:
        if item and r"\python" in item.lower() and os.path.isdir(item):
            return item
    return ""


_ROOT = _qmt_python_dir()
_SOURCE = os.path.join(_ROOT, "BIGQMT_REDIS_DRYRUN.py")
if not os.path.isfile(_SOURCE):
    raise RuntimeError("BIGQMT_BRIDGE requires BIGQMT_REDIS_DRYRUN.py in QMT python directory")

# Execute in this mounted strategy namespace.  QMT injects passorder/cancel/
# get_trade_detail_data here, and the shared loader captures those callbacks.
with open(_SOURCE, "rb") as _stream:
    exec(compile(_stream.read(), _SOURCE, "exec"), globals(), globals())
