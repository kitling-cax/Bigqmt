from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shadow_container_assets_are_present_and_fail_closed():
    directory = ROOT / "container" / "coordinator"
    dockerfile = (directory / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (directory / "entrypoint.sh").read_text(encoding="utf-8")
    compose = (directory / "compose.shadow.yaml").read_text(encoding="utf-8")
    assert "USER 10001:10001" in dockerfile
    assert "SHADOW_READONLY" in entrypoint
    assert "refusing non-shadow" in entrypoint
    assert "192.0.2.121:18666:18443" in compose
    assert "read_only: true" in compose
    assert "BIGQMT_LEASE_GRANTS_DISABLED: \"1\"" in compose


def test_future_production_compose_is_not_a_promotion_path():
    compose = (ROOT / "container" / "coordinator" / "compose.production.yaml").read_text(encoding="utf-8")
    assert "EXPLICIT_FUTURE_PROMOTION_ONLY" in compose
    assert "REQUIRES_FUTURE_IMPLEMENTATION_AND_APPROVAL" in compose
