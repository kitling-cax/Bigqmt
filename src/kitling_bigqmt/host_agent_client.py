"""Outbound read-only Host Agent client for the Coordinator.

The client only posts sanitized heartbeat/snapshot envelopes.  It has no
methods for order intents, Redis commands, QMT RPC, or shell execution.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .host_agent_snapshot import build_heartbeat
from .host_agent_intent_preview import ReadonlyIntentPreview, parse_readonly_intent_preview


@dataclass(frozen=True)
class HostAgentClient:
    endpoint: str
    host_id: str
    timeout_seconds: float = 5.0
    transport: Callable[..., Any] = urlopen

    def heartbeat(self, services: dict[str, str], *, state: str = "HEALTHY_READONLY",
                  account_ids: list[str] | None = None, version: str = "",
                  strategy_instances: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if state != "HEALTHY_READONLY":
            raise ValueError("first Host Agent release is read-only")
        body = build_heartbeat(self.host_id, state, services, account_ids=account_ids, version=version,
                               strategy_instances=strategy_instances)
        request = Request(self.endpoint.rstrip("/") + "/api/v1/hosts/heartbeat",
                          data=json.dumps(body).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        with self.transport(request, timeout=self.timeout_seconds) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload) if payload else {"status": "accepted"}

    def readonly_intent_preview(self, account_id: str) -> ReadonlyIntentPreview:
        """Fetch a future Coordinator preview using GET only.

        This method cannot submit, acknowledge, lease, confirm, execute or
        otherwise mutate an intent.  The initial parser accepts only a
        deliberately empty non-executable response.
        """
        query = urlencode({"account_id": account_id, "host_id": self.host_id})
        request = Request(
            self.endpoint.rstrip("/") + "/api/v1/host-agent/intents?" + query,
            headers={"Accept": "application/json"}, method="GET",
        )
        with self.transport(request, timeout=self.timeout_seconds) as response:
            payload = response.read().decode("utf-8")
        return parse_readonly_intent_preview(
            json.loads(payload), expected_account_id=account_id, expected_host_id=self.host_id
        )
