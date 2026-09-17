"""Read-only status projection for the local BigQMT dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .sleeve_accounting import SleeveAccounting
from .state_store import RuntimeStateStore
from .ops_alerts import build_ops_alerts
from . import machine_config


DEFAULT_BENCHMARK_CODE = "V1.1.17_ETF_POOL"
DEFAULT_BENCHMARK_NAME = "v1.1.17 U25 无酒 ETF 池（等权）"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _latest_lake_cycle(root: Path, environment: str) -> dict[str, Any]:
    """Return a compact local lake-cycle projection; never touches QMT/Redis."""
    evidence_dir = root / "runtime_data" / "evidence" / environment / "lake_cycles"
    paths = sorted(evidence_dir.glob("lake_cycle_*.json"), reverse=True)
    if not paths:
        return {"status": "NOT_RUN", "read_only": True, "orders_enabled": False}
    item = _read_json(paths[0])
    audit = item.get("retention_audit") or {}
    return {
        "status": item.get("status", "UNKNOWN"),
        "evidence_path": str(paths[0]),
        "source_run_id": (item.get("export") or {}).get("source_run_id"),
        "run_count": audit.get("run_count", 0),
        "candidate_count": audit.get("candidate_count", 0),
        "missing_manifest_count": audit.get("missing_manifest_count", 0),
        "read_only": True,
        "orders_enabled": False,
        "broker_call_made": False,
    }


def _latest_bigqmt_raw_release(root: Path, environment: str) -> dict[str, Any]:
    """Project the latest isolated BigQMT Raw release without lake writes."""
    if environment != "simulation":
        return {"status": "NOT_APPLICABLE", "read_only": True, "orders_enabled": False}
    candidates = sorted(
        (p for p in (root / "runtime_data" / "candidates").glob("bigqmt_candidate_*") if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    if not candidates:
        return {"status": "NOT_PUBLISHED", "read_only": True, "orders_enabled": False}
    gate = _read_json(candidates[0] / "final_import_gate.json")
    if not gate:
        return {"status": "CANDIDATE_ONLY", "read_only": True, "orders_enabled": False}
    return {
        "status": gate.get("decision", "UNKNOWN"),
        "release_id": gate.get("release_id"),
        "target": gate.get("published_target"),
        "daily_rows": (gate.get("counts") or {}).get("daily_valid_missing_candidates", 0),
        "intraday_rows": (gate.get("counts") or {}).get("intraday_candidates", 0),
        "tree_hash": (gate.get("gates") or {}).get("published_tree_hash", "PENDING"),
        "roundtrip": (gate.get("gates") or {}).get("published_raw_roundtrip", "PENDING"),
        "pit_status": (gate.get("gates") or {}).get("canonical_pit", "UNKNOWN"),
        "global_latest_updated": bool((gate.get("safety") or {}).get("global_latest_updated", False)),
        "read_only": True,
        "orders_enabled": False,
    }


def _latest_bigqmt_research_pit_release(root: Path, environment: str) -> dict[str, Any]:
    """Project the latest isolated ETF research PIT release without writes.

    This is intentionally separate from the canonical Silver/PIT lake view:
    its release is suitable for the defined U25 research scope only and must
    never be represented as a global ``LATEST`` replacement.
    """
    if environment != "simulation":
        return {"status": "NOT_APPLICABLE", "read_only": True, "orders_enabled": False}
    candidates = sorted(
        (p for p in (root / "runtime_data" / "candidates").glob("bigqmt_etf_research_pit_*") if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    if not candidates:
        return {"status": "NOT_PUBLISHED", "read_only": True, "orders_enabled": False}
    candidate = candidates[0]
    candidate_manifest = _read_json(candidate / "manifest.json")
    release_id = str(candidate_manifest.get("release_id") or candidate.name)
    default_lake = Path(r"C:\BigQMT\research\quant_data_lake")
    published = _read_json(
        default_lake / "silver" / "_bigqmt_research_pit_releases" / release_id / "publish_manifest.json"
    )
    if not published:
        return {
            "status": "CANDIDATE_ONLY", "release_id": release_id,
            "rows": candidate_manifest.get("rows", 0), "codes": len((candidate_manifest.get("scope") or {}).get("codes") or []),
            "global_latest_updated": False, "read_only": True, "orders_enabled": False,
        }
    return {
        "status": published.get("status", "UNKNOWN"), "release_id": release_id,
        "target": published.get("target"), "rows": published.get("rows", 0), "codes": published.get("codes", 0),
        "events": published.get("events", 0), "research_backtest": published.get("research_backtest", "PENDING"),
        "pit_scope": published.get("pit_scope", "ETF split-only conservative available_at policy"),
        "tree_hash": published.get("tree_hash", "PENDING"),
        "global_latest_updated": bool(published.get("global_latest_updated", False)),
        "legacy_silver_bars_pit_modified": bool(published.get("legacy_silver_bars_pit_modified", False)),
        "read_only": True, "orders_enabled": False,
    }


def _latest_daily_sleeve(root: Path, strategy_id: str) -> dict[str, Any]:
    """Read the latest immutable closing valuation without QMT/Redis access."""
    directory = root / "runtime_data" / "evidence" / "simulation" / "daily_operations"
    for path in sorted(directory.glob("v1_1_15_daily_*.json"), reverse=True):
        report = _read_json(path)
        sleeve = report.get("sleeve")
        if isinstance(sleeve, dict) and sleeve.get("strategy_id") == strategy_id:
            return sleeve
    return {}


def _with_security_names(summary: dict[str, Any], security_names: dict[str, Any]) -> dict[str, Any]:
    """Attach display names to a read-only sleeve projection."""
    result = dict(summary)
    result["positions"] = [
        {**dict(position), "display_name": str(security_names.get(str(position.get("stock_code"))) or position.get("stock_code") or "")}
        for position in list(summary.get("positions") or [])
        if isinstance(position, dict)
    ]
    return result


def _sleeve_metrics(summary: dict[str, Any], nav_series: list[dict[str, Any]], benchmark_series: list[dict[str, Any]],
                    benchmark_code: str = DEFAULT_BENCHMARK_CODE,
                    benchmark_name: str = DEFAULT_BENCHMARK_NAME) -> dict[str, Any]:
    """Compute display-only account metrics from durable sleeve snapshots."""
    initial = float(summary.get("initial_capital") or 0.0)
    nav_values = [initial] + [float(point.get("net_asset_value") or 0.0) for point in nav_series]
    peak = 0.0
    maximum_drawdown = 0.0
    for value in nav_values:
        peak = max(peak, value)
        if peak > 0:
            maximum_drawdown = max(maximum_drawdown, (peak - value) / peak)
    prior = float(nav_series[-2].get("net_asset_value")) if len(nav_series) >= 2 else initial
    current = float(summary.get("net_asset_value") or 0.0)
    benchmark = benchmark_series[-1] if benchmark_series else {}
    return {
        "initial_capital": initial,
        "net_asset_value": current,
        "total_pnl": float(summary.get("total_pnl") or 0.0),
        "return_rate": float(summary.get("return_rate") or 0.0),
        "daily_pnl": current - prior,
        "daily_return_rate": current / prior - 1 if prior > 0 else 0.0,
        "maximum_drawdown": maximum_drawdown,
        "position_count": len(summary.get("positions") or []),
        "benchmark_code": benchmark_code,
        "benchmark_name": benchmark_name,
        "benchmark_return_rate": benchmark.get("return_rate"),
        "excess_return_rate": (
            float(summary.get("return_rate") or 0.0) - float(benchmark.get("return_rate"))
            if benchmark.get("return_rate") is not None else None
        ),
    }


def _formal_strategy_recovery(root: Path) -> dict[str, Any]:
    """Return non-authoritative, display-only formal recovery status.

    The dashboard must never treat this as a capability: only the future
    execution admission path can grant per-strategy order authority.
    """
    policy = _read_json(root / "config" / "strategy_runtime_policy.json")
    admissions = _read_json(root / "config" / "formal_strategy_admissions.json")
    approved = admissions.get("approved_strategies")
    if not isinstance(approved, list):
        approved = []
    intent = bool(((policy.get("production") or {}).get("strategy_recovery_enabled")))
    return {
        "recovery_intent_enabled": intent,
        "admitted_strategy_count": len(approved),
        "orders_enabled": False,
        "status": "INTENT_ON_NO_ADMISSION" if intent and not approved else (
            "NOT_AUTHORIZED" if not intent else "ADMISSION_REVIEW_REQUIRED"
        ),
    }


def build_dashboard_status(root: Path, profile: str = "simulation") -> dict[str, Any]:
    """Return a safe local status view without contacting QMT or Redis.

    The formal projection deliberately reads only its own state database.  It
    must never fall back to simulation sleeves, signals, or account snapshots.
    """
    if profile not in {"simulation", "production_readonly"}:
        raise ValueError("unsupported dashboard profile")
    current = _read_json(root / "progress" / "current_status.json")
    blockers = _read_json(root / "progress" / "blockers.json")
    tests = _read_json(root / "progress" / "latest_tests.json")
    is_simulation = profile == "simulation"
    active_blockers = [item for item in blockers.get("blockers", []) if item.get("status") == "ACTIVE"] if is_simulation else []
    recent = list(tests.get("tests", []))[-8:] if is_simulation else []
    config = machine_config.load_gateway(root, profile)
    environment = str((current.get("environment") if is_simulation else "") or config.get("environment") or "simulation")
    security_names = _read_json(root / "config" / "security_names.json")
    registry = _read_json(root / "config" / "strategy_registry.json")
    benchmark_config = _read_json(root / "config" / "v1_1_17_etf_pool.json")
    benchmark_code = str(benchmark_config.get("benchmark_code") or DEFAULT_BENCHMARK_CODE)
    benchmark_name = str(benchmark_config.get("display_name") or DEFAULT_BENCHMARK_NAME)
    registry_rows = []
    registry_by_id: dict[str, dict[str, Any]] = {}
    for item in registry.get("strategies", []):
        if not isinstance(item, dict):
            continue
        # Formal dashboard never projects simulation-only registry entries.
        if not is_simulation and item.get("formal_account_allowed") is not True:
            continue
        row = {
            key: item.get(key)
            for key in (
                "strategy_id", "display_name", "source_project", "source_domain", "asset_class",
                "version", "status", "initial_capital", "max_capital", "sleeve_id",
                "allowed_accounts", "formal_account_allowed", "execution_enabled", "universe",
                "signal_contract",
            )
        }
        registry_rows.append(row)
        registry_by_id[str(row.get("strategy_id") or "")] = row
    snapshot: dict[str, Any] = {}
    quote_summary: dict[str, Any] = {}
    strategy_sleeves: list[dict[str, Any]] = []
    strategy_shadows: list[dict[str, Any]] = []
    state_path = config.get("state_db")
    if isinstance(state_path, str) and state_path:
        try:
            store = RuntimeStateStore(Path(state_path), Path(config.get("audit_dir") or root / "runtime_data" / "audit"))
            latest = store.latest_snapshot_bundle()
            snapshot_metadata = store.latest_snapshot_metadata()
            quote_summary = store.quote_freshness_summary(1)
            if latest:
                run_id, bundle = latest
                asset = (bundle.get("asset") or {}).get("data") or {}
                positions = (bundle.get("positions") or {}).get("data") or {}
                display_positions = {}
                for code, position in positions.items():
                    row = dict(position or {})
                    raw_name = str(row.get("stock_name") or "")
                    mapped_name = str(security_names.get(str(code)) or "")
                    row["display_name"] = mapped_name or (raw_name if "�" not in raw_name else "")
                    display_positions[str(code)] = row
                snapshot = {
                    "run_id": run_id,
                    "captured_at": (snapshot_metadata or {}).get("completed_at", ""),
                    "capture_status": (snapshot_metadata or {}).get("status", "UNKNOWN"),
                    "bridge_version": (snapshot_metadata or {}).get("bridge_version", ""),
                    "total_asset": asset.get("total_asset"), "cash": asset.get("cash"),
                    "market_value": asset.get("market_value"), "position_count": len(positions),
                    "order_count": len((bundle.get("orders") or {}).get("data") or []),
                    "trade_count": len((bundle.get("trades") or {}).get("data") or []),
                    "positions": display_positions,
                    "orders": (bundle.get("orders") or {}).get("data") or [],
                    "trades": (bundle.get("trades") or {}).get("data") or [],
                }
            else:
                positions = {}
            prices = {
                str(code): float((row or {}).get("price"))
                for code, row in positions.items()
                if isinstance(row, dict) and (row or {}).get("price") not in (None, "")
            }
            ledger = SleeveAccounting(store)
            if is_simulation:
                strategy_shadows = store.latest_strategy_shadow_events(limit=20)
            with store.session() as db:
                sleeve_ids = [str(row[0]) for row in db.execute(
                    "SELECT strategy_id FROM strategy_sleeves ORDER BY strategy_id"
                ).fetchall()]
            for strategy_id in sleeve_ids:
                try:
                    summary = ledger.summary(strategy_id, prices)
                    series = ledger.nav_series(strategy_id, limit=365)
                    benchmark_series = ledger.benchmark_series(strategy_id, benchmark_code, limit=365)
                    daily_summary = _latest_daily_sleeve(root, strategy_id) if is_simulation else None
                    if daily_summary:
                        summary = daily_summary
                    summary = _with_security_names(summary, security_names)
                    registry_item = registry_by_id.get(strategy_id, {})
                    strategy_sleeves.append({
                        "summary": summary,
                        "nav_series": series,
                        "benchmark_series": benchmark_series,
                        "metrics": _sleeve_metrics(summary, series, benchmark_series, benchmark_code, benchmark_name),
                        "display_name": registry_item.get("display_name") or strategy_id,
                        "version": registry_item.get("version") or "—",
                        "status": registry_item.get("status") or "ACTIVE_ACCOUNT",
                    })
                except (OSError, ValueError):
                    strategy_sleeves.append({
                        "summary": {"strategy_id": strategy_id, "status": "VALUATION_UNAVAILABLE",
                                     "orders_enabled": False},
                        "nav_series": [],
                        "benchmark_series": [],
                        "metrics": {},
                        "display_name": registry_by_id.get(strategy_id, {}).get("display_name") or strategy_id,
                    })
        except (OSError, ValueError, json.JSONDecodeError):
            snapshot = {"status": "UNAVAILABLE"}
    account_id = str(config.get("account_id") or "")
    masked_account = ("***" + account_id[-4:]) if account_id else "unknown"
    lake_cycle = _latest_lake_cycle(root, environment)
    bigqmt_raw_release = _latest_bigqmt_raw_release(root, environment)
    bigqmt_research_pit_release = _latest_bigqmt_research_pit_release(root, environment)
    bridge = str(current.get("bridge", "unknown")) if is_simulation else "BIGQMT_BRIDGE_PRODUCTION_READONLY"
    ops_alerts = build_ops_alerts(
        bridge=bridge, orders_enabled=False,
        quote_summary=quote_summary, active_blockers=active_blockers, lake_cycle=lake_cycle,
    )
    return {
        "schema_version": 1,
        "service": "kitling_bigqmt_dashboard",
        "profile": profile,
        "read_only": True,
        "orders_enabled": False,
        "order_actions_exposed": False,
        "environment": environment,
        "stage": current.get("stage", "unknown") if is_simulation else "P13_FORMAL_READONLY_OBSERVABILITY",
        "stage_status": current.get("stage_status", "unknown") if is_simulation else "READ_ONLY",
        "bridge": bridge,
        "account": {"display_id": masked_account, "type": config.get("account_type", "unknown")},
        "snapshot": snapshot,
        "strategy_sleeves": strategy_sleeves,
        "strategy_shadows": strategy_shadows,
        "strategy_registry": registry_rows,
        "formal_strategy_recovery": _formal_strategy_recovery(root) if not is_simulation else {},
        "lake_cycle": lake_cycle,
        "bigqmt_raw_release": bigqmt_raw_release,
        "bigqmt_research_pit_release": bigqmt_research_pit_release,
        "ops_alerts": ops_alerts,
        "quote_summary": quote_summary,
        "runtime_ownership": current.get("runtime_ownership", {}) if is_simulation else {"production_runtime": "BIGQMT_TRAY_ONLY"},
        "next_gate": current.get("next_gate", "") if is_simulation else "正式账户仅做本地只读投影；不显示策略信号，且不提供下单或撤单能力。",
        "active_blockers": active_blockers,
        "recent_tests": recent,
    }
