import hashlib

from scripts.build_openclaw_standalone_readonly_bundle import build


def test_standalone_bundle_is_portable_and_has_lf_stable_readme(tmp_path):
    output = tmp_path / "release"
    manifest = build(output)

    assert manifest["release"] == "openclaw-bigqmt-bundle-0.1.3-readonly"
    assert manifest["scope"] == "observer_readonly"
    assert manifest["orders_enabled"] is False
    assert manifest["requires"] == {"python": ">=3.11", "bigqmt_project": False}

    readme = output / "README_INSTALL.md"
    assert b"\r\n" not in readme.read_bytes()
    assert b"\r\n" not in (output / "manifest.json").read_bytes()
    assert b"\r\n" not in (output / "checksums.sha256").read_bytes()

    expected = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    assert len(expected) == 6
    for relative_path, expected_hash in expected.items():
        actual = hashlib.sha256((output / relative_path).read_bytes()).hexdigest()
        assert actual == expected_hash
