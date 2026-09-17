import json

from kitling_bigqmt.host_agent_client import HostAgentClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"status":"accepted","mode":"readonly"}'


def test_client_posts_only_readonly_heartbeat():
    seen = {}

    def transport(request, timeout):
        seen["url"] = request.full_url
        seen["method"] = request.method
        seen["body"] = json.loads(request.data)
        seen["timeout"] = timeout
        return FakeResponse()

    result = HostAgentClient("http://127.0.0.1:18443", "192.0.2.105", transport=transport).heartbeat(
        {"qmt": "UP", "redis": "UP"}, account_ids=["90000001"])
    assert result["status"] == "accepted"
    assert seen["url"].endswith("/api/v1/hosts/heartbeat")
    assert seen["method"] == "POST"
    assert seen["body"]["state"] == "HEALTHY_READONLY"
    assert "password" not in seen["body"]
    assert "orders" not in seen["body"]
