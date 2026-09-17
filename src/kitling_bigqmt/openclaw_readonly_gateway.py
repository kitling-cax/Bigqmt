"""Strictly read-only Coordinator tools exposed through a local MCP adapter."""
from __future__ import annotations

import json
from typing import Any
from urllib.request import urlopen


TOOLS = (
    {
        "name": "bigqmt_get_fleet_status",
        "description": "Read BigQMT host, account and service heartbeat state.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "endpoint": "/api/v1/hosts",
    },
    {
        "name": "bigqmt_get_executor_preview",
        "description": "Read simulation executor candidates and lease state; no lease is changed.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "endpoint": "/api/v1/executor-preview",
    },
    {
        "name": "bigqmt_get_project_progress",
        "description": "Read the BigQMT multi-host project phase from Coordinator.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "endpoint": "/api/v1/progress",
    },
)


def tool_catalog() -> list[dict[str, Any]]:
    return [{key: value for key, value in tool.items() if key != "endpoint"} for tool in TOOLS]


def call_readonly_tool(name: str, arguments: dict[str, Any], endpoint: str, *, timeout: float = 5.0) -> dict[str, Any]:
    tool = next((item for item in TOOLS if item["name"] == name), None)
    if tool is None:
        raise ValueError("tool is not exposed")
    if arguments:
        raise ValueError("this read-only tool accepts no arguments")
    url = endpoint.rstrip("/") + str(tool["endpoint"])
    with urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {"tool": name, "readonly": True, "orders_enabled": False, "source": url, "payload": payload}
