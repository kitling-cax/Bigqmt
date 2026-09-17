"""Safe promotion of an isolated research release inside a v2 channel.

This is deliberately narrower than a global Silver/PIT publisher: it can only
move one non-global research-channel pointer after validating an immutable
release.  The legacy catalog and ``GLOBAL_PIT_V2`` are never writable here.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ResearchCatalogV2Error(ValueError):
    """Raised when a research pointer promotion is unsafe."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchCatalogV2Error("unreadable JSON %s: %s" % (path, exc)) from exc
    if not isinstance(payload, dict):
        raise ResearchCatalogV2Error("JSON root must be an object: %s" % path)
    return payload


def validate_isolated_release(release_path: Path, lake_root: Path) -> dict[str, Any]:
    """Validate an already-published U25 research release without loading it all."""
    release = Path(release_path).resolve()
    root = Path(lake_root).resolve()
    expected_parent = (root / "silver" / "_bigqmt_research_pit_releases").resolve()
    try:
        release.relative_to(expected_parent)
    except ValueError as exc:
        raise ResearchCatalogV2Error("release is outside isolated research root") from exc
    manifest = _load_json(release / "publish_manifest.json")
    if manifest.get("status") != "PUBLISHED_ISOLATED_RESEARCH_PIT":
        raise ResearchCatalogV2Error("release is not an isolated published research PIT")
    if manifest.get("global_latest_updated") is not False:
        raise ResearchCatalogV2Error("release claims a global catalog update")
    if manifest.get("legacy_silver_bars_pit_modified") is not False:
        raise ResearchCatalogV2Error("release modified legacy Silver PIT")
    if manifest.get("orders_enabled") is not False:
        raise ResearchCatalogV2Error("research release must have orders disabled")
    if not list((release / "daily").rglob("*.parquet")):
        raise ResearchCatalogV2Error("research release has no parquet data")
    return manifest


def promote_isolated_research_release(
    catalog_path: Path,
    channel: str,
    release_path: Path,
    *,
    expected_previous_release: str | None,
    contract_sha256: str,
) -> dict[str, Any]:
    """Atomically move one isolated channel pointer with an immutable backup.

    ``expected_previous_release`` is a compare-and-swap guard.  Supplying it
    prevents a stale daily updater from overwriting a newer researcher choice.
    The caller must supply a contract hash generated from the reviewed v2
    contract; that keeps the catalog and policy version aligned.
    """
    catalog = Path(catalog_path).resolve()
    if catalog.name != "LATEST_RESEARCH.json" or catalog.parent.name != "catalog" or catalog.parent.parent.name != "v2":
        raise ResearchCatalogV2Error("only v2/catalog/LATEST_RESEARCH.json is writable")
    lake_root = catalog.parent.parent.parent
    payload = _load_json(catalog)
    if payload.get("schema_version") != 2 or payload.get("global_latest_updated") is not False:
        raise ResearchCatalogV2Error("catalog is not a safe v2 research catalog")
    if channel == "GLOBAL_PIT_V2":
        raise ResearchCatalogV2Error("global PIT cannot be promoted by research publisher")
    entry = (payload.get("channels") or {}).get(channel)
    if not isinstance(entry, dict) or entry.get("global_default") is not False:
        raise ResearchCatalogV2Error("channel is missing or not isolated")
    current = entry.get("current_release")
    if expected_previous_release != current:
        raise ResearchCatalogV2Error("expected previous release does not match catalog")
    manifest = validate_isolated_release(release_path, lake_root)
    release = str(Path(release_path).resolve())
    if current == release:
        return {"status": "NO_CHANGE", "channel": channel, "release": release,
                "global_latest_updated": False, "orders_enabled": False}

    backup_dir = catalog.parent / "history"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_dir / ("LATEST_RESEARCH_" + stamp + ".json")
    backup.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    next_payload = dict(payload)
    next_channels = dict(payload.get("channels") or {})
    next_entry = dict(entry)
    next_entry["current_release"] = release
    next_entry["release_id"] = manifest.get("release_id")
    next_entry["promoted_at"] = datetime.now(timezone.utc).isoformat()
    next_entry["global_default"] = False
    next_channels[channel] = next_entry
    next_payload["channels"] = next_channels
    next_payload["contract_sha256"] = str(contract_sha256)
    next_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    next_payload["global_latest_updated"] = False
    next_payload["legacy_catalog_latest_modified"] = False
    next_payload["orders_enabled"] = False

    temporary = catalog.with_name(catalog.name + ".tmp")
    try:
        temporary.write_text(json.dumps(next_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, catalog)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"status": "PROMOTED_ISOLATED_RESEARCH_RELEASE", "channel": channel,
            "previous_release": current, "release": release, "backup": str(backup),
            "global_latest_updated": False, "orders_enabled": False}
