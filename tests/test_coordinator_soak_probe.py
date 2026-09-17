from __future__ import annotations

import json

from scripts.coordinator.soak_probe import sample


def test_sample_fails_closed_when_endpoints_unavailable(tmp_path):
    output = tmp_path / "soak.jsonl"
    result = sample("http://127.0.0.1:1", "http://127.0.0.1:2", 0.1)
    output.write_text(json.dumps(result), encoding="utf-8")
    assert result["ok"] is False
    assert result["readonly"] is True
    assert result["orders_enabled"] is False

