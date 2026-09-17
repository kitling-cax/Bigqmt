"""Pure-local, read-only operational alert projection."""

from __future__ import annotations

from typing import Any


def build_ops_alerts(
    *,
    bridge: str,
    orders_enabled: bool,
    quote_summary: dict[str, Any],
    active_blockers: list[dict[str, Any]],
    lake_cycle: dict[str, Any],
) -> dict[str, Any]:
    alerts: list[dict[str, Any]] = []

    def add(alert_id: str, severity: str, message: str) -> None:
        alerts.append({"id": alert_id, "severity": severity, "message": message, "read_only": True})

    if orders_enabled:
        add("ORDERS_ENABLED_UNEXPECTED", "CRITICAL", "订单开关异常为开启，必须保持 fail-closed。")
    upper_bridge = str(bridge).upper()
    if any(token in upper_bridge for token in ("UNAVAILABLE", "ERROR", "DISCONNECTED")):
        add("BRIDGE_UNAVAILABLE", "CRITICAL", f"QMT Bridge 状态异常：{bridge}")
    stale = int(quote_summary.get("states", {}).get("STALE", 0) or 0)
    unknown = int(quote_summary.get("states", {}).get("UNKNOWN", 0) or 0)
    if stale:
        add("QUOTE_STALE", "WARNING", f"行情陈旧样本 {stale} 个，禁止据此生成交易信号。")
    if unknown:
        add("QUOTE_UNKNOWN", "WARNING", f"行情未知样本 {unknown} 个，禁止据此生成交易信号。")
    lake_status = str(lake_cycle.get("status") or "NOT_RUN")
    if lake_status not in ("PASSED", "NOT_RUN"):
        add("LAKE_CYCLE_BLOCKED", "WARNING", f"数据湖周期状态：{lake_status}。")
    for blocker in active_blockers:
        add(str(blocker.get("id") or "ACTIVE_BLOCKER"), "WARNING", str(blocker.get("description") or "存在活动阻塞。"))
    rank = {"CRITICAL": 3, "WARNING": 2, "INFO": 1}
    highest = max((item["severity"] for item in alerts), key=lambda value: rank[value], default="INFO")
    return {"alerts": alerts, "alert_count": len(alerts), "highest_severity": highest, "read_only": True}
