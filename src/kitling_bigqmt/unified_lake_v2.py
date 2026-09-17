"""Initialize and validate the source-preserving unified research-lake v2.

The module deliberately only creates a new ``v2`` catalog skeleton.  It does
not ingest a bar, contact QMT/Redis, mutate the legacy lake, or alter any
global LATEST pointer.  Future importers must write immutable candidates and
pass the data-quality gates defined in the contract before promotion.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTRACT_FILE = "unified_data_lake_v2_contract.json"
CATALOG_FILE = "LATEST_RESEARCH.json"
BASELINE_FILE = "BASELINE.json"
REQUIRED_GATES = (
    "stock_raw", "etf_raw", "pit_adjustment", "universe_pit",
    "source_freshness", "service_health", "manifest_hash",
)


class UnifiedLakeV2Error(ValueError):
    """Raised when a v2 catalog or release violates its fail-closed contract."""


def load_contract(path: Path) -> dict[str, Any]:
    """Read and minimally validate the human-reviewed v2 contract."""
    try:
        contract = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnifiedLakeV2Error("contract is unreadable: %s" % exc) from exc
    if contract.get("schema_version") != 2:
        raise UnifiedLakeV2Error("unsupported v2 contract schema")
    if contract.get("release_policy", {}).get("copy_on_write") is not True:
        raise UnifiedLakeV2Error("v2 must use copy-on-write")
    gates = tuple(contract.get("release_policy", {}).get("required_gates") or ())
    if gates != REQUIRED_GATES:
        raise UnifiedLakeV2Error("required data-quality gate set changed")
    if contract.get("safety", {}).get("legacy_catalog_latest_modified") is not False:
        raise UnifiedLakeV2Error("v2 contract must not modify legacy LATEST")
    return contract


def contract_sha256(contract: dict[str, Any]) -> str:
    payload = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def catalog_payload(contract: dict[str, Any], contract_path: Path) -> dict[str, Any]:
    """Build a fixed, non-global research-channel catalog payload."""
    channels = contract.get("research_channels") or {}
    return {
        "schema_version": 2,
        "kind": "unified_research_catalog",
        "status": "FOUNDATION_ONLY_NO_GLOBAL_PIT_V2_RELEASE",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract": str(Path(contract_path).resolve()),
        "contract_sha256": contract_sha256(contract),
        "channels": channels,
        "selection_rule": "research must select a channel/release_id and filter available_at <= asof",
        "global_latest_updated": False,
        "legacy_catalog_latest_modified": False,
        "orders_enabled": False,
    }


def initialize(lake_root: Path, contract_path: Path) -> dict[str, Any]:
    """Create only an idempotent v2 skeleton below ``lake_root/v2``.

    An existing catalog is accepted only when it uses the same contract hash;
    this prevents a retry from silently replacing a release-selection policy.
    """
    contract = load_contract(contract_path)
    root = Path(lake_root).resolve() / "v2"
    catalog_dir = root / "catalog"
    expected = catalog_payload(contract, contract_path)
    catalog_path = catalog_dir / CATALOG_FILE
    created = False
    if catalog_path.exists():
        try:
            existing = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UnifiedLakeV2Error("existing v2 catalog is unreadable: %s" % exc) from exc
        if existing.get("contract_sha256") != expected["contract_sha256"]:
            raise UnifiedLakeV2Error("existing v2 catalog has a different contract; inspect before migration")
    else:
        for relative in (
            "bronze/bars", "bronze/corporate_actions", "silver/raw_canonical/releases",
            "silver/pit_v2/releases", "silver/universe_pit_v2/releases", "gold", "_staging", "catalog",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
        baseline = {
            "schema_version": 2,
            "kind": "unified_lake_v2_baseline",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "contract_sha256": expected["contract_sha256"],
            "purpose": "Empty v2 foundation; no source bars, company actions or global PIT were imported.",
            "legacy_data_modified": False,
            "global_latest_updated": False,
            "orders_enabled": False,
        }
        (catalog_dir / BASELINE_FILE).write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
        created = True
    return {
        "status": "INITIALIZED" if created else "ALREADY_INITIALIZED",
        "v2_root": str(root),
        "catalog": str(catalog_path),
        "contract_sha256": expected["contract_sha256"],
        "global_latest_updated": False,
        "legacy_catalog_latest_modified": False,
        "orders_enabled": False,
    }


def evaluate_release_gates(gates: dict[str, str]) -> dict[str, Any]:
    """Fail closed unless every contract gate has an explicit PASSED status."""
    missing = [gate for gate in REQUIRED_GATES if gate not in gates]
    failed = {gate: gates.get(gate) for gate in REQUIRED_GATES if gates.get(gate) != "PASSED"}
    return {
        "required_gates": list(REQUIRED_GATES),
        "missing_gates": missing,
        "failed_or_nonpassed_gates": failed,
        "publishable": not missing and not failed,
        "decision": "READY_FOR_EXPLICIT_GLOBAL_RELEASE" if not missing and not failed else "CANDIDATE_ONLY",
    }
