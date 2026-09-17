"""Persistent read-only Host Agent loop for heartbeat and intent polling.

This module is a testable scheduler.  It never imports QMT, Redis, the bridge
or a broker client.  It posts a sanitized heartbeat and performs a GET-only
intent preview.  In M03 the preview is always empty and no order action may be
taken; any non-empty or non-read-only response is surfaced as an error and no
execution path is opened.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .host_agent_account_policy import resolve_account_policy
from .host_agent_client import HostAgentClient


@dataclass
class HostAgentLoop:
    client: HostAgentClient
    profile: str
    heartbeat_interval_seconds: float = 30.0
    intent_poll_interval_seconds: float = 30.0
    heartbeat_services_provider: Callable[[], dict[str, str]] | None = None
    _last_heartbeat: float = field(default=float("-inf"), init=False)
    _last_intent: float = field(default=float("-inf"), init=False)

    def __post_init__(self) -> None:
        self.account_id = resolve_account_policy(self.profile).account_id

    def _clock(self) -> float:
        return time.monotonic()

    def tick(self, now: float | None = None) -> dict[str, Any]:
        now = self._clock() if now is None else float(now)
        result: dict[str, Any] = {
            "orders_enabled": False,
            "heartbeat_sent": False,
            "intent_polled": False,
            "intent_count": 0,
            "errors": [],
        }

        if now - self._last_heartbeat >= self.heartbeat_interval_seconds:
            services = (
                self.heartbeat_services_provider()
                if self.heartbeat_services_provider is not None
                else {}
            )
            try:
                self.client.heartbeat(services, account_ids=[self.account_id])
                result["heartbeat_sent"] = True
            except Exception as exc:  # coordinator outage must not stop tray
                result["errors"].append({"phase": "heartbeat", "error": type(exc).__name__})
            self._last_heartbeat = now

        if now - self._last_intent >= self.intent_poll_interval_seconds:
            try:
                preview = self.client.readonly_intent_preview(self.account_id)
                result["intent_polled"] = True
                result["intent_count"] = len(preview.intents)
                if preview.orders_enabled:
                    result["errors"].append(
                        {"phase": "intent", "error": "UNEXPECTED_ORDERS_ENABLED"}
                    )
            except Exception as exc:  # fail closed on any non-empty/executable shape
                result["errors"].append({"phase": "intent", "error": type(exc).__name__})
            self._last_intent = now

        return result

    def run_forever(self, stop_event: Any = None, sleep_s: float = 1.0) -> None:
        """Blocking loop for standalone use; the tray instead drives tick()."""
        while stop_event is None or not stop_event.is_set():
            self.tick()
            time.sleep(sleep_s)
