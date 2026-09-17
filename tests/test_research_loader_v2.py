import json
from pathlib import Path

import pandas as pd
import pytest

from kitling_bigqmt.research_loader_v2 import ResearchLakeV2Error, duckdb_query_pit, load_pit_asof


def _catalog(tmp_path: Path) -> Path:
    release = tmp_path / "u25_release"
    (release / "daily" / "year=2026").mkdir(parents=True)
    frame = pd.DataFrame({
        "code": ["510300.SH", "510300.SH"],
        "trade_date": ["20260101", "20260102"], "close": [4.0, 4.1],
        "available_at": ["2026-01-02T01:30:00Z", "2026-01-03T01:30:00Z"],
        "row_hash": ["a", "b"],
    })
    frame.to_parquet(release / "daily" / "year=2026" / "part.parquet", index=False)
    (release / "publish_manifest.json").write_text(json.dumps({"global_latest_updated": False}), encoding="utf-8")
    catalog = tmp_path / "LATEST_RESEARCH.json"
    catalog.write_text(json.dumps({"schema_version": 2, "global_latest_updated": False,
                                   "channels": {"U25": {"current_release": str(release)}}}), encoding="utf-8")
    return catalog


def test_loader_filters_available_at_before_duckdb_query(tmp_path):
    catalog = _catalog(tmp_path)
    meta, frame = load_pit_asof(catalog, "U25", "2026-01-02T15:30:00+08:00")
    assert len(frame) == 1
    assert meta["channel"] == "U25"
    result = duckdb_query_pit(catalog, "U25", "2026-01-02T15:30:00+08:00", "select count(*) as n from pit")
    assert int(result.iloc[0]["n"]) == 1


def test_loader_rejects_naive_asof_and_unapproved_global_channel(tmp_path):
    catalog = _catalog(tmp_path)
    with pytest.raises(ResearchLakeV2Error, match="timezone"):
        load_pit_asof(catalog, "U25", "2026-01-02")
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    payload["channels"]["GLOBAL"] = {"current_release": None}
    catalog.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ResearchLakeV2Error, match="no approved"):
        load_pit_asof(catalog, "GLOBAL", "2026-01-02T15:30:00+08:00")
