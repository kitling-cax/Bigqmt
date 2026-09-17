"""Read-only quality gate for v1.1.15 close-shadow evidence."""

from __future__ import annotations

from typing import Any


def assess_shadow_events(events: list[dict[str, Any]], required_days: int = 1, min_bar_count: int = 25) -> dict[str, Any]:
    """Assess durable shadow records without deciding execution admission.

    The report remains useful for data/state continuity.  It is deliberately
    not an order gate: v1.1.15 simulation execution is authorised separately
    through its live preflight and short QMT runtime-control window.
    """
    if required_days < 1 or min_bar_count < 1:
        raise ValueError("required_days and min_bar_count must be positive")
    ordered = sorted(events, key=lambda row: str(row.get("signal_day") or ""))
    unique_days = sorted({str(row.get("signal_day") or "") for row in ordered if row.get("signal_day")})
    safety_errors: list[str] = []
    coverage_errors: list[str] = []
    continuity_errors: list[str] = []
    for index, event in enumerate(ordered):
        day = str(event.get("signal_day") or "unknown")
        if event.get("orders_enabled") is not False or event.get("broker_call_made") is not False:
            safety_errors.append(f"{day}: order/broker safety field is not false")
        if event.get("execution_intent") != "NONE_CLOSE_SIGNAL_ONLY":
            safety_errors.append(f"{day}: unexpected execution_intent")
        coverage = event.get("bar_coverage") if isinstance(event.get("bar_coverage"), dict) else {}
        insufficient = sorted(str(code) for code, count in coverage.items() if int(count or 0) < min_bar_count)
        if not coverage:
            coverage_errors.append(f"{day}: missing bar coverage")
        elif insufficient:
            coverage_errors.append(f"{day}: insufficient bars for {', '.join(insufficient)}")
        if index and event.get("state_before") != ordered[index - 1].get("state_after"):
            continuity_errors.append(f"{day}: state_before does not match prior state_after")
    complete = len(unique_days) >= required_days and not safety_errors and not coverage_errors and not continuity_errors
    return {
        "schema_version": 1,
        "kind": "v1_1_15_close_shadow_evidence_assessment",
        "recorded_days": unique_days,
        "recorded_day_count": len(unique_days),
        "required_days": required_days,
        "remaining_days": max(0, required_days - len(unique_days)),
        "min_bar_count": min_bar_count,
        "safety_errors": safety_errors,
        "coverage_errors": coverage_errors,
        "continuity_errors": continuity_errors,
        "evidence_complete": complete,
        "orders_enabled": False,
        "broker_call_made": False,
        "simulation_order_admission": "NOT_DECIDED_BY_SHADOW_EVIDENCE",
        "reason": "shadow evidence is informational; simulation execution uses a separate live account/quote/sleeve preflight and short-lived QMT runtime window",
    }
