import json

from scripts.host_agent.collect_runtime_fact import build_runtime_fact
from kitling_bigqmt.coordinator_outbox import LocalOutbox


def test_collect_runtime_fact_is_local_and_orders_locked(tmp_path):
    audit = tmp_path / "native_tray.jsonl"
    audit.write_text(
        json.dumps({
            "event_time": "2026-09-17T04:13:09Z",
            "event": "status_refreshed",
            "detail": "在线; Redis 正常｜看板 正常｜订单锁定",
            "orders_enabled": False,
            "execution_consumer_enabled": False,
        }) + "\n",
        encoding="utf-8",
    )
    payload = build_runtime_fact(profile="simulation", host_id="192.0.2.105", audit_path=audit)
    assert payload["account_id"] == "90000001"
    assert payload["state"] == "RUNNING"
    assert payload["orders_enabled"] is False
    outbox = LocalOutbox(tmp_path / "outbox.sqlite3")
    result = outbox.enqueue("STRATEGY_RUNTIME", payload)
    assert result["status"] == "QUEUED"
    assert len(outbox.pending()) == 1


def test_collect_runtime_fact_is_idempotent_for_same_audit(tmp_path):
    audit = tmp_path / "native_tray.jsonl"
    audit.write_text('{"event_time":"2026-09-17T04:13:09Z","event":"status_refreshed"}\n', encoding="utf-8")
    first = build_runtime_fact(profile="production_readonly", host_id="192.0.2.105", audit_path=audit)
    second = build_runtime_fact(profile="production_readonly", host_id="192.0.2.105", audit_path=audit)
    assert first["event_id"] == second["event_id"]
    assert first["account_id"] == "90000002"
    assert first["orders_enabled"] is False


def test_collect_runtime_fact_id_ignores_unrelated_file_growth(tmp_path):
    audit = tmp_path / "native_tray.jsonl"
    first_line = '{"event_time":"2026-09-17T04:13:09Z","event":"status_refreshed"}'
    audit.write_text(first_line + "\n", encoding="utf-8")
    first = build_runtime_fact(profile="simulation", host_id="192.0.2.105", audit_path=audit)
    audit.write_text(first_line + "\n" + '{"event_time":"2026-09-17T04:14:09Z","event":"other"}\n', encoding="utf-8")
    second = build_runtime_fact(profile="simulation", host_id="192.0.2.105", audit_path=audit)
    assert first["event_id"] != second["event_id"]
    audit.write_text(first_line + "\n" + '{"event_time":"2026-09-17T04:14:09Z","event":"other"}\n' + first_line + "\n", encoding="utf-8")
    third = build_runtime_fact(profile="simulation", host_id="192.0.2.105", audit_path=audit)
    assert first["event_id"] == third["event_id"]
