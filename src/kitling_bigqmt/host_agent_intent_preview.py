"""Fail-closed parser for a future Host Agent intent-preview response.

This is deliberately *not* an order consumer.  It allows the Windows Host
Agent to perform an authenticated GET in a later deployment and show why an
intent would be rejected, while every returned item stays non-executable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class IntentPreviewRejected(ValueError):
    """The response cannot be treated as a safe read-only preview."""


@dataclass(frozen=True)
class ReadonlyIntentPreview:
    account_id: str
    host_id: str
    intents: tuple[dict[str, Any], ...]
    orders_enabled: bool


def parse_readonly_intent_preview(
    payload: dict[str, Any] | None, *, expected_account_id: str, expected_host_id: str
) -> ReadonlyIntentPreview:
    """Accept only an explicit empty/read-only Coordinator preview envelope.

    The initial API contract intentionally permits no intent rows.  A future
    execution rollout must introduce a separately reviewed contract and never
    silently reinterpret this parser as an order authorization.
    """
    if not isinstance(payload, dict):
        raise IntentPreviewRejected("intent preview is missing")
    if payload.get("mode") != "readonly-intent-preview":
        raise IntentPreviewRejected("unexpected intent preview mode")
    if payload.get("readonly") is not True or payload.get("orders_enabled") is not False:
        raise IntentPreviewRejected("intent preview is not explicitly read-only")
    if str(payload.get("account_id", "")) != expected_account_id:
        raise IntentPreviewRejected("intent preview account mismatch")
    if str(payload.get("host_id", "")) != expected_host_id:
        raise IntentPreviewRejected("intent preview host mismatch")
    intents = payload.get("intents")
    if not isinstance(intents, list):
        raise IntentPreviewRejected("intent preview intents must be a list")
    if intents:
        raise IntentPreviewRejected("read-only preview must not contain executable intents")
    return ReadonlyIntentPreview(expected_account_id, expected_host_id, (), False)
