import json
from pathlib import Path

import pytest

from kitling_bigqmt.research_catalog_v2 import ResearchCatalogV2Error, promote_isolated_research_release


def _catalog_and_release(tmp_path: Path):
    lake = tmp_path / "lake"
    catalog = lake / "v2" / "catalog" / "LATEST_RESEARCH.json"
    catalog.parent.mkdir(parents=True)
    old = lake / "silver" / "_bigqmt_research_pit_releases" / "old"
    new = lake / "silver" / "_bigqmt_research_pit_releases" / "new"
    for path, release_id in ((old, "old"), (new, "new")):
        (path / "daily" / "year=2026").mkdir(parents=True)
        (path / "daily" / "year=2026" / "part.parquet").write_bytes(b"placeholder")
        (path / "publish_manifest.json").write_text(json.dumps({
            "release_id": release_id, "status": "PUBLISHED_ISOLATED_RESEARCH_PIT",
            "global_latest_updated": False, "legacy_silver_bars_pit_modified": False,
            "orders_enabled": False,
        }), encoding="utf-8")
    catalog.write_text(json.dumps({
        "schema_version": 2, "global_latest_updated": False,
        "channels": {"U25": {"current_release": str(old), "global_default": False}},
    }), encoding="utf-8")
    return catalog, old, new


def test_isolated_promotion_uses_cas_backup_and_never_global(tmp_path):
    catalog, old, new = _catalog_and_release(tmp_path)
    result = promote_isolated_research_release(catalog, "U25", new,
                                                expected_previous_release=str(old), contract_sha256="abc")
    assert result["status"] == "PROMOTED_ISOLATED_RESEARCH_RELEASE"
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    assert payload["channels"]["U25"]["current_release"] == str(new.resolve())
    assert payload["global_latest_updated"] is False
    assert payload["orders_enabled"] is False
    assert Path(result["backup"]).is_file()


def test_isolated_promotion_rejects_stale_or_global(tmp_path):
    catalog, old, new = _catalog_and_release(tmp_path)
    with pytest.raises(ResearchCatalogV2Error, match="expected previous"):
        promote_isolated_research_release(catalog, "U25", new,
                                           expected_previous_release="wrong", contract_sha256="abc")
    with pytest.raises(ResearchCatalogV2Error, match="global PIT"):
        promote_isolated_research_release(catalog, "GLOBAL_PIT_V2", new,
                                           expected_previous_release=None, contract_sha256="abc")
