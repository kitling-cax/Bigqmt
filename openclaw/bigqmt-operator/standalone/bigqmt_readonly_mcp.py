"""Standalone, dependency-free BigQMT observer MCP over stdio JSON-RPC.

It requires only Python 3.11+ and a local non-secret endpoint configuration.
No BigQMT project checkout, QMT installation or token is required.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen


TOOLS = (
    ("bigqmt_get_fleet_status", "Read BigQMT host, account and service heartbeat state.", "/api/v1/hosts"),
    ("bigqmt_get_executor_preview", "Read executor candidates and lease state; no lease is changed.", "/api/v1/executor-preview"),
    ("bigqmt_get_project_progress", "Read BigQMT multi-host project progress.", "/api/v1/progress"),
)


def endpoint() -> str:
    override = os.environ.get("BIGQMT_COORDINATOR_ENDPOINT", "").strip()
    if override:
        return override.rstrip("/")
    config = Path(__file__).with_name("bigqmt_readonly.local.json")
    if config.is_file():
        try:
            value = str(json.loads(config.read_text(encoding="utf-8")).get("coordinator_endpoint") or "").strip()
            if value:
                return value.rstrip("/")
        except (OSError, ValueError):
            pass
    raise ValueError("coordinator endpoint is not configured")


def tools() -> list[dict]:
    return [{"name": name, "description": description,
             "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}
            for name, description, _ in TOOLS]


def invoke(name: str, arguments: dict) -> dict:
    route = next((path for tool_name, _, path in TOOLS if tool_name == name), None)
    if route is None:
        raise ValueError("tool is not exposed")
    if arguments:
        raise ValueError("read-only tools accept no arguments")
    source = endpoint() + route
    with urlopen(source, timeout=5.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {"tool": name, "readonly": True, "orders_enabled": False, "source": source, "payload": payload}


def reply(request: dict) -> dict | None:
    method, request_id = request.get("method"), request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "bigqmt-readonly", "version": "0.1.1"}, "capabilities": {"tools": {}}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools()}}
    if method == "tools/call":
        params = request.get("params") or {}
        try:
            payload = invoke(str(params.get("name", "")), dict(params.get("arguments") or {}))
            result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "isError": False}
        except Exception as exc:
            result = {"content": [{"type": "text", "text": json.dumps({"status": "DEGRADED", "reason": type(exc).__name__, "orders_enabled": False}, ensure_ascii=False)}], "isError": True}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}}


def main() -> int:
    for line in sys.stdin:
        try:
            response = reply(json.loads(line))
            if response is not None:
                print(json.dumps(response, ensure_ascii=False), flush=True)
        except ValueError:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
