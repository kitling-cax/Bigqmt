from scripts.build_openclaw_readonly_bundle import build


def test_bundle_is_immutable_and_observer_only(tmp_path):
    output = tmp_path / "release"
    manifest = build(output)
    assert manifest["orders_enabled"] is False
    assert manifest["scope"] == "observer_readonly"
    assert (output / "skill" / "SKILL.md").is_file()
    assert (output / "checksums.sha256").is_file()
