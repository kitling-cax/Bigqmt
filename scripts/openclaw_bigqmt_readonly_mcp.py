"""Dependency-free stdio JSON-RPC MCP adapter for BigQMT read-only tools.

Messages are one JSON object per line, compatible with local stdio MCP
launchers.  This process has no order, lease-write, Redis, QMT or shell tool.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.coordinator_endpoint import resolve_coordinator  # noqa: E402
from kitling_bigqmt.openclaw_readonly_gateway import call_readonly_tool, tool_catalog  # noqa: E402


def _result(request_id: object, value: object) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _error(request_id: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(request: dict) -> dict | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _result(request_id, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "bigqmt-readonly", "version": "0.1.0"}, "capabilities": {"tools": {}}})
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": tool_catalog()})
    if method == "tools/call":
        params = request.get("params") or {}
        endpoint, _ = resolve_coordinator(ROOT)
        try:
            value = call_readonly_tool(str(params.get("name", "")), dict(params.get("arguments") or {}), endpoint)
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "isError": False})
        except Exception as exc:
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps({"status": "DEGRADED", "reason": type(exc).__name__, "orders_enabled": False}, ensure_ascii=False)}], "isError": True})
    return _error(request_id, -32601, "method not found")


def main() -> int:
    for line in sys.stdin:
        try:
            reply = handle(json.loads(line))
            if reply is not None:
                print(json.dumps(reply, ensure_ascii=False), flush=True)
        except json.JSONDecodeError:
            print(json.dumps(_error(None, -32700, "parse error")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
