"""Release-aware, as-of-safe readers for the unified v2 research lake."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


class ResearchLakeV2Error(ValueError):
    pass


def load_catalog(catalog_path: Path) -> dict[str, Any]:
    try:
        catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchLakeV2Error("research catalog is unreadable: %s" % exc) from exc
    if catalog.get("schema_version") != 2 or catalog.get("global_latest_updated") is not False:
        raise ResearchLakeV2Error("catalog is not a safe v2 research catalog")
    return catalog


def resolve_channel(catalog_path: Path, channel: str, release_id: str | None = None) -> tuple[dict[str, Any], Path]:
    catalog = load_catalog(catalog_path)
    entry = (catalog.get("channels") or {}).get(channel)
    if not entry:
        raise ResearchLakeV2Error("unknown research channel: %s" % channel)
    selected = entry.get("current_release")
    if release_id is not None:
        if not selected or Path(selected).name != release_id:
            raise ResearchLakeV2Error("requested release_id is not the approved channel release")
    if not selected:
        raise ResearchLakeV2Error("research channel has no approved release: %s" % channel)
    path = Path(selected).resolve()
    if not path.exists():
        raise ResearchLakeV2Error("approved release path does not exist: %s" % path)
    return entry, path


def load_pit_asof(catalog_path: Path, channel: str, asof: str, release_id: str | None = None) -> tuple[dict[str, Any], pd.DataFrame]:
    """Load an explicitly selected PIT release and enforce timezone-aware as-of."""
    cutoff = pd.Timestamp(asof)
    if cutoff.tzinfo is None:
        raise ResearchLakeV2Error("asof must include a timezone")
    entry, release = resolve_channel(catalog_path, channel, release_id)
    manifest_path = release / "publish_manifest.json"
    if not manifest_path.is_file():
        raise ResearchLakeV2Error("release manifest missing: %s" % release)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("global_latest_updated") is not False:
        raise ResearchLakeV2Error("release violates isolated/global safety contract")
    paths = sorted(release.rglob("*.parquet"))
    if not paths:
        raise ResearchLakeV2Error("release has no parquet data: %s" % release)
    frame = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    required = {"code", "trade_date", "close", "available_at", "row_hash"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ResearchLakeV2Error("release missing fields: %s" % ",".join(missing))
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.loc[frame["available_at"] <= cutoff.tz_convert("UTC")].sort_values(["code", "trade_date"]).reset_index(drop=True)
    # Pandas 3 may expose plain text columns with dtype ``str``; DuckDB's
    # dataframe bridge currently accepts object/string-extension columns but
    # not that dtype label.  Convert only textual columns, leaving timestamps
    # and numeric research values untouched.
    for column in frame.columns:
        if str(frame[column].dtype) == "str":
            frame[column] = frame[column].astype(object)
    return {"channel": channel, "entry": entry, "release": manifest, "asof": cutoff.isoformat()}, frame


def duckdb_query_pit(catalog_path: Path, channel: str, asof: str, sql: str,
                     release_id: str | None = None) -> pd.DataFrame:
    """Run a read-only DuckDB query over the already as-of-filtered PIT frame."""
    import duckdb

    _, frame = load_pit_asof(catalog_path, channel, asof, release_id)
    connection = duckdb.connect(":memory:")
    try:
        connection.register("pit", frame)
        return connection.execute(sql).df()
    finally:
        connection.close()
