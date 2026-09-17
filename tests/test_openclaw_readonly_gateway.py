import json
from io import StringIO

import pytest

from kitling_bigqmt.openclaw_readonly_gateway import TOOLS, call_readonly_tool, tool_catalog


def test_gateway_catalog_contains_only_readonly_coordinator_tools():
    names = {item["name"] for item in tool_catalog()}
    assert names == {"bigqmt_get_fleet_status", "bigqmt_get_executor_preview", "bigqmt_get_project_progress"}
    assert all("endpoint" not in item for item in tool_catalog())


def test_gateway_rejects_unknown_tool_and_arguments():
    with pytest.raises(ValueError, match="not exposed"):
        call_readonly_tool("bigqmt_confirm_order", {}, "http://127.0.0.1:1")
    with pytest.raises(ValueError, match="no arguments"):
        call_readonly_tool("bigqmt_get_fleet_status", {"account": "90000001"}, "http://127.0.0.1:1")
