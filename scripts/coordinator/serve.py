"""Read-only Coordinator bootstrap service.

Only health/readiness/progress endpoints are exposed in this milestone.  No
QMT, Redis, order, shell, or OpenClaw integration is imported here.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(os.environ.get("BIGQMT_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.coordinator_core import CoordinatorStore  # noqa: E402
from kitling_bigqmt.coordinator_instance import (  # noqa: E402
    CoordinatorInstanceLock,
    load_or_create_identity,
)
from kitling_bigqmt.host_fact_identity import trusted_hosts_from_file  # noqa: E402
from kitling_bigqmt.coordinator_fact_ingress import CoordinatorFactIngress  # noqa: E402
from kitling_bigqmt.strategy_catalog import list_candidates, preview_push  # noqa: E402
from kitling_bigqmt.strategy_catalog_page import catalog_html  # noqa: E402
from kitling_bigqmt.strategy_deployment import StrategyDeploymentStore  # noqa: E402

HOST = os.environ.get("BIGQMT_COORDINATOR_BIND", "127.0.0.1")
PORT = int(os.environ.get("BIGQMT_COORDINATOR_PORT", "18443"))
COORDINATOR_MODE = os.environ.get("BIGQMT_COORDINATOR_MODE", "READONLY_FOUNDATION").strip().upper()
COORDINATOR_INSTANCE_ID = os.environ.get("BIGQMT_COORDINATOR_INSTANCE_ID", "UNINITIALIZED")
HOSTS: dict[str, dict] = {}
HOSTS_LOCK = threading.Lock()
try:
    PROFILE_TTL_SECONDS = max(1, int(os.environ.get("BIGQMT_PROFILE_TTL_SECONDS", "120")))
except ValueError:
    PROFILE_TTL_SECONDS = 120
ACCOUNT_POLICY = {
    "90000001": {"mode": "SIMULATION", "execution_eligible": True},
    "90000002": {"mode": "PRODUCTION_READ_ONLY", "execution_eligible": False},
}
# Deployment (real) account IDs -> stable internal profile keys are supplied
# by the Coordinator operator through gitignored config/machine.local.json
# (section coordinator.deployment_account_aliases), never hardcoded here.
# Real account IDs must not live in the public source tree.  Absent mapping on
# a deployment degrades to the identity mapping, so the operator must provide
# the alias table on the Coordinator for its account-policy checks to apply.
def _load_account_aliases() -> dict[str, str]:
    try:
        from kitling_bigqmt.machine_config import load_machine_local

        machine = load_machine_local(ROOT)
        aliases = (machine.get("coordinator") or {}).get("deployment_account_aliases") or {}
        if isinstance(aliases, dict):
            return {str(k): str(v) for k, v in aliases.items() if str(k).strip() and str(v).strip()}
    except Exception:
        pass
    return {}


ACCOUNT_ALIASES = _load_account_aliases()
REQUIRED_EXECUTOR_SERVICES = ("qmt", "redis", "bridge", "tray")


def account_alias_status() -> dict:
    """Return an operator-safe configuration check without deployment IDs."""
    profile_keys = sorted({value for value in ACCOUNT_ALIASES.values()
                           if value in ACCOUNT_POLICY})
    return {
        "configured": bool(ACCOUNT_ALIASES),
        "configured_alias_count": len(ACCOUNT_ALIASES),
        "profile_keys": profile_keys,
    }


def _strategy_visibility_snapshot() -> dict:
    """Flatten sanitized strategy observations and derive web-only alerts.

    This is intentionally a projection: it never changes a local Key, tray
    policy, lease, order switch, or running process.
    """
    hosts = _live_hosts_snapshot()
    instances = []
    for host in hosts:
        for account_id, report in (host.get("profiles") or {}).items():
            for item in report.get("strategy_instances", []) if isinstance(report, dict) else []:
                if not isinstance(item, dict):
                    continue
                instances.append({
                    "host_id": host.get("host_id"), "account_id": account_id,
                    "strategy_id": item.get("strategy_id"), "version": item.get("version", ""),
                    "state": item.get("state", "UNKNOWN"),
                    "policy_enabled": bool(item.get("policy_enabled", False)),
                    "authorization_key_state": item.get("authorization_key_state", "UNKNOWN"),
                    "bridge_version": item.get("bridge_version", ""),
                    "sent_at": report.get("sent_at"),
                })
    alerts = []
    by_account_key: dict[str, set[str]] = {}
    by_account_strategy: dict[tuple[str, str], set[str]] = {}
    by_account: dict[str, set[str]] = {}
    for row in instances:
        account = str(row["account_id"])
        host = str(row["host_id"])
        if row["authorization_key_state"] == "VALID":
            by_account_key.setdefault(account, set()).add(host)
        if row["state"] == "RUNNING":
            strategy = str(row["strategy_id"])
            by_account_strategy.setdefault((account, strategy), set()).add(host)
            by_account.setdefault(account, set()).add(strategy)
    for account, hosts_for_key in by_account_key.items():
        if len(hosts_for_key) > 1:
            alerts.append({"code": "ACCOUNT_AUTHORIZATION_KEY_ON_MULTIPLE_HOSTS", "severity": "WARNING",
                           "account_id": account, "host_ids": sorted(hosts_for_key),
                           "action": "WEB_ALERT_ONLY_NO_AUTO_DOWNGRADE"})
    for (account, strategy), hosts_for_strategy in by_account_strategy.items():
        if len(hosts_for_strategy) > 1:
            alerts.append({"code": "DUPLICATE_STRATEGY_RUNNING_ON_MULTIPLE_HOSTS", "severity": "CRITICAL",
                           "account_id": account, "strategy_id": strategy,
                           "host_ids": sorted(hosts_for_strategy),
                           "action": "WEB_ALERT_ONLY_NO_AUTO_STOP"})
    for account, strategies in by_account.items():
        if len(strategies) > 1:
            alerts.append({"code": "MULTIPLE_STRATEGIES_RUNNING_ON_ACCOUNT", "severity": "WARNING",
                           "account_id": account, "strategy_ids": sorted(strategies),
                           "action": "WEB_ALERT_ONLY_NO_AUTO_STOP"})
    return {"status": "ok", "readonly": True, "orders_enabled": False,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "instances": instances, "alerts": alerts,
            "control": "VISIBILITY_PROJECTION_NO_POLICY_OR_ORDER_WRITE"}


def coordinator_store() -> CoordinatorStore:
    """Obtain the durable lease store without exposing a write HTTP API."""
    default = "/var/lib/kitling-bigqmt-coordinator/coordinator.sqlite3"
    if os.name == "nt":
        default = str(ROOT / "runtime_data" / "coordinator" / "coordinator.sqlite3")
    return CoordinatorStore(os.environ.get("BIGQMT_COORDINATOR_DB", default))


def strategy_deployment_store() -> StrategyDeploymentStore:
    return StrategyDeploymentStore(os.environ.get("BIGQMT_COORDINATOR_DB", "/var/lib/kitling-bigqmt-coordinator/coordinator.sqlite3"))


def strategy_install_requests(payload: dict) -> tuple[int, dict]:
    """Create pull-based install requests; never creates an execution lease."""
    if not isinstance(payload, dict):
        return 400, {"status": "rejected", "reason": "request must be an object"}
    strategy_id = str(payload.get("strategy_id", ""))
    version = str(payload.get("version", ""))
    build_id = str(payload.get("build_id", ""))
    requested_by = str(payload.get("requested_by") or "dashboard")
    targets = payload.get("target_host_ids")
    if not isinstance(targets, list) or not targets:
        return 400, {"status": "rejected", "reason": "target_host_ids is required"}
    candidates = list_candidates(ROOT).get("candidates", [])
    candidate = next((item for item in candidates if item.get("strategy_id") == strategy_id
                      and item.get("version") == version and item.get("build_id") == build_id), None)
    if not candidate or candidate.get("status") != "READY":
        return 400, {"status": "rejected", "reason": "strategy candidate is not READY",
                      "orders_enabled": False}
    live_ids = {str(host.get("host_id")) for host in _live_hosts_snapshot() if host.get("host_id")}
    store = strategy_deployment_store()
    deployments = []
    for host_id in dict.fromkeys(str(value).strip() for value in targets):
        if not host_id:
            return 400, {"status": "rejected", "reason": "target host id is empty", "orders_enabled": False}
        if host_id not in live_ids:
            return 409, {"status": "rejected", "reason": "target host is not connected",
                         "target_host_id": host_id, "orders_enabled": False}
        deployments.append(store.request_install(
            strategy_id=strategy_id, version=version, build_id=build_id,
            manifest_sha256=str(candidate.get("manifest_sha256") or ""),
            package_path=str(candidate.get("package_path") or ""),
            target_host_id=host_id, requested_by=requested_by,
        ))
    return 202, {
        "status": "INSTALL_REQUESTED", "readonly": False, "orders_enabled": False,
        "install_started": False, "run_after_install": False, "deployments": deployments,
        "control": "HOST_AGENT_PULLS_AND_VERIFIES_NO_AUTO_START",
    }


def fact_ingress_from_environment() -> CoordinatorFactIngress | None:
    """Build the optional authenticated fact sink; disabled unless explicit.

    Secrets are supplied through the service/container secret mechanism as a
    protected JSON file. No default secret or fallback identity exists.
    """
    if os.environ.get("BIGQMT_FACT_INGEST_ENABLED", "0") != "1":
        return None
    secret_file = os.environ.get("BIGQMT_FACT_TRUSTED_HOSTS_FILE", "").strip()
    if not secret_file:
        raise ValueError("fact ingest enabled without trusted hosts")
    try:
        trusted = trusted_hosts_from_file(secret_file)
    except (TypeError, ValueError, OSError) as exc:
        raise ValueError("invalid trusted fact host configuration") from exc
    if not trusted:
        raise ValueError("trusted host list is empty")
    return CoordinatorFactIngress(coordinator_store().database_path, trusted)


def _heartbeat_age_seconds(sent_at: object, now: datetime | None = None) -> int | None:
    try:
        value = datetime.fromisoformat(str(sent_at).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0, int(((now or datetime.now(timezone.utc)) - value).total_seconds()))
    except (TypeError, ValueError):
        return None


def _prune_stale_profiles_locked(now: datetime | None = None) -> int:
    """Remove stale/invalid account profiles and rebuild host account indexes.

    The in-memory registry is deliberately ephemeral.  A profile is live only
    while its own sanitized heartbeat remains within ``PROFILE_TTL_SECONDS``.
    This prevents an old host/account identity from becoming an execution
    candidate after a tray is moved, renamed, or stopped.  Transaction data,
    Redis state, and the durable lease database are not touched here.

    ``HOSTS_LOCK`` must be held by the caller.
    """
    current = now or datetime.now(timezone.utc)
    removed = 0
    for host_id, host in list(HOSTS.items()):
        raw_profiles = host.get("profiles", {})
        if not isinstance(raw_profiles, dict):
            removed += 1
            HOSTS.pop(host_id, None)
            continue
        live_profiles: dict[str, dict] = {}
        for account_id, report in raw_profiles.items():
            if not isinstance(report, dict):
                removed += 1
                continue
            age = _heartbeat_age_seconds(report.get("sent_at"), current)
            if age is None or age > PROFILE_TTL_SECONDS:
                removed += 1
                continue
            live_profiles[str(account_id)] = report
        if not live_profiles:
            # A host with no live account profile is not useful to the fleet
            # view and must not remain an apparent executor candidate.
            HOSTS.pop(host_id, None)
            continue
        host["profiles"] = live_profiles
        host["accounts"] = sorted(
            account_id for account_id in live_profiles if account_id != "unbound"
        )
        # Keep the host-level timestamp coherent with the newest surviving
        # profile, even when an older second tray was pruned.
        timestamps = [
            report.get("sent_at") for report in live_profiles.values()
            if _heartbeat_age_seconds(report.get("sent_at"), current) is not None
        ]
        if timestamps:
            host["sent_at"] = max(timestamps)
    return removed


def _live_hosts_snapshot() -> list[dict]:
    """Return a pruned, detached fleet snapshot for every read endpoint."""
    with HOSTS_LOCK:
        _prune_stale_profiles_locked()
        return deepcopy(list(HOSTS.values()))


def _profile_reaper() -> None:
    """Continuously age out profiles even when no dashboard request arrives."""
    interval = max(1, min(30, PROFILE_TTL_SECONDS // 2 or 1))
    while True:
        time.sleep(interval)
        with HOSTS_LOCK:
            _prune_stale_profiles_locked()


DEFAULT_PROGRAM_PHASE = "M01_M04_READONLY_FLEET_IMPLEMENTATION_IN_PROGRESS"
DEFAULT_VERIFIED_PERCENT = 15


def _scan_program_yaml(path: Path) -> dict:
    """Dependency-free scan of the two scalar program fields (no YAML lib)."""
    data: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        # Match only top-level (column-0) keys: indented milestone "status:"
        # lines must not overwrite the whole-program phase.
        if line.startswith("status:"):
            data["phase"] = line[len("status:"):].strip()
        elif line.startswith("overall_verified_percent:"):
            try:
                data["overall_verified_percent"] = int(line[len("overall_verified_percent:"):].strip())
            except ValueError:
                pass
        elif line.startswith("updated_at:"):
            data["updated_at"] = line[len("updated_at:"):].strip()
    return data


def load_progress() -> dict:
    """Read the deployed program-phase snapshot; fails open with a safe default."""
    explicit = os.environ.get("BIGQMT_COORDINATOR_PHASE_FILE", "").strip()
    state_path = Path("/var/lib/kitling-bigqmt-coordinator/progress.json")
    yaml_path = ROOT / "progress" / "multi_host_program.yaml"
    candidates: list[Path] = []
    if os.name == "nt":
        candidates = [yaml_path, ROOT / "runtime_data" / "coordinator" / "progress.json", state_path]
    else:
        candidates = [state_path, yaml_path]
    if explicit:
        candidates.insert(0, Path(explicit))
    for path in candidates:
        if not path.is_file():
            continue
        try:
            if path.suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("phase"):
                    return data
            else:
                data = _scan_program_yaml(path)
                if data.get("phase"):
                    return data
        except (OSError, json.JSONDecodeError):
            continue
    return {
        "phase": os.environ.get("BIGQMT_COORDINATOR_PHASE", DEFAULT_PROGRAM_PHASE),
        "overall_verified_percent": DEFAULT_VERIFIED_PERCENT,
    }


def executor_preview() -> dict:
    """Project candidates only; no lease is written in the bootstrap service."""
    hosts = _live_hosts_snapshot()
    store = coordinator_store()
    entries = []
    for account_id, policy in ACCOUNT_POLICY.items():
        lease = store.current_lease(account_id)
        lease_valid = bool(lease and lease.mode == "ACTIVE_EXECUTOR" and lease.expires_at > datetime.now(timezone.utc).timestamp())
        current_executor = lease.host_id if lease_valid else None
        lease_state = "ACTIVE" if lease_valid else ("EXPIRED" if lease else "UNASSIGNED_READONLY")
        candidates = []
        for host in hosts:
            report = dict(host.get("profiles", {})).get(account_id)
            if not report:
                continue
            services = report.get("services", {})
            age_seconds = _heartbeat_age_seconds(report.get("sent_at"))
            healthy = age_seconds is not None and age_seconds <= 90 and all(
                services.get(name) == "UP" for name in REQUIRED_EXECUTOR_SERVICES
            )
            candidates.append({
                "host_id": host.get("host_id"),
                "eligible": bool(policy["execution_eligible"] and healthy and not lease_valid),
                "health_reason": (
                    "LEASE_ALREADY_ACTIVE" if lease_valid else
                    ("HEALTHY_READONLY" if healthy else "STALE_OR_SERVICE_DOWN")
                ),
                "heartbeat_age_seconds": age_seconds,
            })
        entries.append({
            "account_id": account_id,
            "account_mode": policy["mode"],
            "current_executor": current_executor,
            "lease_state": lease_state,
            "fencing_token": lease.token if lease_valid else None,
            "coordinator_epoch": lease.epoch if lease_valid else store.epoch(),
            "expires_at": lease.expires_at if lease_valid else None,
            "candidates": candidates,
            "control": "PREVIEW_ONLY_NO_LEASE_WRITE",
        })
    return {
        "status": "ok",
        "mode": "readonly-preview",
        "profile_ttl_seconds": PROFILE_TTL_SECONDS,
        "accounts": entries,
    }


def host_agent_intent_preview(account_id: str, host_id: str) -> tuple[int, dict]:
    """Return a deliberately empty, non-executable Host Agent inbox.

    This endpoint is the first M03 connectivity seam only.  It never reads
    Coordinator intents, leases, QMT, Redis, or any broker state.  A future
    order-intent rollout requires a distinct authorized endpoint and contract.
    """
    account_id = ACCOUNT_ALIASES.get(account_id, account_id)
    if account_id not in ACCOUNT_POLICY or not host_id.strip():
        return 400, {"status": "rejected", "reason": "invalid_preview_scope"}
    return 200, {
        "status": "ok",
        "mode": "readonly-intent-preview",
        "readonly": True,
        "orders_enabled": False,
        "account_id": account_id,
        "host_id": host_id,
        "intents": [],
        "control": "EMPTY_PREVIEW_NO_INTENT_READ_OR_EXECUTION",
    }


def host_agent_intent_preview_status() -> dict:
    """Aggregate only the visible empty-preview state for the monitor page."""
    hosts = _live_hosts_snapshot()
    targets = []
    for host in hosts:
        for account_id in sorted(dict(host.get("profiles", {}))):
            targets.append({
                "host_id": host.get("host_id"),
                "account_id": account_id,
                "state": "EMPTY_READONLY",
                "intent_count": 0,
                "orders_enabled": False,
            })
    return {
        "status": "ok", "mode": "readonly-intent-preview-status", "readonly": True,
        "orders_enabled": False, "profile_ttl_seconds": PROFILE_TTL_SECONDS,
        "targets": targets,
        "control": "EMPTY_PREVIEW_NO_INTENT_READ_OR_EXECUTION",
    }


def coordinator_dashboard_html() -> str:
    """Small dependency-free, read-only Coordinator monitor page."""
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BigQMT Coordinator</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#172033;font:14px "Segoe UI","Microsoft YaHei",sans-serif}.top{background:#fff;border-bottom:1px solid #e4e9f0;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;gap:16px}.brand{font-size:20px;font-weight:700}.sub{color:#64748b;margin-top:4px}.chip{border:1px solid #b9ddc9;background:#edfbf2;color:#147a50;border-radius:999px;padding:6px 10px;font-size:12px}main{max-width:1240px;margin:0 auto;padding:24px}.summary{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:14px;margin-bottom:18px}.metric,.host{background:#fff;border:1px solid #e1e7ef;border-radius:12px;box-shadow:0 2px 8px rgba(30,41,59,.04)}.metric{padding:16px}.label{font-size:12px;color:#64748b}.value{font-size:24px;font-weight:700;margin-top:8px}.host{padding:18px;margin-top:14px}.hosthead{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.hostid{font-size:17px;font-weight:700}.note{color:#64748b;font-size:12px;margin-top:5px}.mode{background:#fff7e5;border:1px solid #f1d398;color:#925d00;border-radius:999px;padding:5px 9px;font-size:12px;white-space:nowrap}.profiles{display:grid;grid-template-columns:repeat(2,minmax(270px,1fr));gap:12px;margin-top:16px}.profile{border:1px solid #e4e9f0;border-radius:10px;padding:14px}.profile h3{font-size:14px;margin:0 0 10px}.services{display:flex;flex-wrap:wrap;gap:7px}.service{font-size:12px;border-radius:6px;padding:5px 7px;background:#f1f5f9;color:#475569}.service.up{background:#ecfdf3;color:#157a50}.service.down{background:#fff1f2;color:#b42318}.empty{padding:38px;text-align:center;color:#64748b;background:#fff;border:1px dashed #cbd5e1;border-radius:12px}.foot{margin-top:18px;color:#64748b;font-size:12px}@media(max-width:700px){.top{padding:15px 18px}.summary,.profiles{grid-template-columns:1fr}main{padding:16px}}
</style></head><body><header class="top"><div><div class="brand">BigQMT Coordinator</div><div class="sub">多主机托盘与账户状态 · 只读监控</div></div><div class="chip">订单控制未开放</div></header><main><section class="summary"><div class="metric"><div class="label">在线主机</div><div class="value" id="hostCount">—</div></div><div class="metric"><div class="label">已上报账户</div><div class="value" id="accountCount">—</div></div><div class="metric"><div class="label">ACTIVE_EXECUTOR</div><div class="value" id="executor">未分配</div></div><div class="metric"><div class="label">Intent Preview</div><div class="value" id="intentPreview">—</div></div></section><div id="alerts" class="host" style="display:none"></div><div id="hosts" class="empty">正在读取 Coordinator 状态…</div><div class="foot">每 30 秒由账户托盘发送脱敏只读心跳。页面每 10 秒刷新；不含凭据、订单或策略控制。</div></main><script>
const labels={qmt:'QMT',miniqmt:'MiniQMT',redis:'Redis',bridge:'Bridge',dashboard:'Dashboard',tray:'Tray'};
function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function render(data){const hosts=Array.isArray(data.hosts)?data.hosts:[];document.getElementById('hostCount').textContent=hosts.length;const accounts=new Set(hosts.flatMap(h=>h.accounts||[]));document.getElementById('accountCount').textContent=accounts.size;const root=document.getElementById('hosts');root.replaceChildren();if(!hosts.length){root.className='empty';root.textContent='尚未收到任何托盘心跳';return}root.className='';for(const host of hosts){const card=node('section','host');const head=node('div','hosthead');const title=node('div');title.append(node('div','hostid',host.host_id),node('div','note','最后心跳：'+(host.sent_at||'—')+' · '+(host.state||'UNKNOWN')));head.append(title,node('span','mode','只读监控'));card.append(head);const profiles=host.profiles||{};const grid=node('div','profiles');for(const account of Object.keys(profiles).sort()){const report=profiles[account]||{};const box=node('article','profile');box.append(node('h3','',account));const services=node('div','services');for(const key of Object.keys(labels)){const value=(report.services||{})[key]||'UNKNOWN';services.append(node('span','service '+value.toLowerCase(),labels[key]+' '+value));}box.append(services, node('div','note','更新时间：'+(report.sent_at||'—')));grid.append(box)}card.append(grid);root.append(card)}}
async function refresh(){try{const [h,e,i,a]=await Promise.all([fetch('/api/v1/hosts',{cache:'no-store'}),fetch('/api/v1/executor-preview',{cache:'no-store'}),fetch('/api/v1/host-agent/intent-preview-status',{cache:'no-store'}),fetch('/api/v1/alerts',{cache:'no-store'})]);if(!h.ok||!e.ok||!i.ok||!a.ok)throw Error();const hosts=await h.json(),preview=await e.json(),intents=await i.json(),alerts=await a.json();const eligible=(preview.accounts||[]).flatMap(a=>a.candidates||[]).filter(c=>c.eligible).length;document.getElementById('executor').textContent=eligible?'未分配（'+eligible+' 候选）':'未分配';document.getElementById('intentPreview').textContent=(intents.orders_enabled===false?'空队列／只读':'异常');const alertBox=document.getElementById('alerts');const rows=alerts.alerts||[];alertBox.style.display=rows.length?'block':'none';alertBox.innerHTML=rows.length?'<b>运行告警（仅网页提示，不自动停机）</b><ul>'+rows.map(x=>'<li>'+x.code+' · 账户 '+x.account_id+' · '+(x.host_ids||[]).join(', ')+'</li>').join('')+'</ul>':'';render(hosts)}catch{document.getElementById('hosts').className='empty';document.getElementById('hosts').textContent='Coordinator 暂不可达'}}refresh();setInterval(refresh,10000);
</script></body></html>"""


def response_payload(path: str) -> tuple[int, dict]:
    if path == "/healthz":
        return 200, {
            "status": "ok",
            "service": "kitling-bigqmt-coordinator",
            "mode": COORDINATOR_MODE.lower(),
            "account_alias_configuration": account_alias_status(),
        }
    if path == "/readyz":
        return 200, {"status": "ready", "mode": COORDINATOR_MODE.lower(), "database": "not-enabled-in-bootstrap"}
    if path == "/api/v1/instance":
        return 200, {
            "status": "ok", "readonly": True, "orders_enabled": False,
            "mode": COORDINATOR_MODE.lower(), "coordinator_instance_id": COORDINATOR_INSTANCE_ID,
            "control": "INSTANCE_IDENTITY_ONLY_NO_LEASE_OR_ORDER_WRITE",
        }
    if path == "/api/v1/progress":
        snapshot = load_progress()
        return 200, {
            "status": "ok",
            "readonly": True,
            "orders_enabled": False,
            "phase": snapshot.get("phase"),
            "overall_verified_percent": snapshot.get("overall_verified_percent"),
            "updated_at": snapshot.get("updated_at"),
        }
    if path == "/api/v1/strategy-candidates":
        return 200, list_candidates(ROOT)
    if path == "/api/v1/strategy-deployments":
        return 400, {"status": "rejected", "reason": "host_id query is required", "orders_enabled": False}
    if path == "/api/v1/executor-preview":
        return 200, executor_preview()
    if path == "/api/v1/fleet":
        hosts = _live_hosts_snapshot()
        return 200, {
            "status": "ok",
            "mode": "readonly-fleet",
            "readonly": True,
            "orders_enabled": False,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "profile_ttl_seconds": PROFILE_TTL_SECONDS,
            "hosts": hosts,
            "executor_preview": executor_preview(),
            "intent_preview": host_agent_intent_preview_status(),
            "progress": load_progress(),
            "control": "READ_ONLY_FLEET_PROJECTION",
        }
    if path == "/api/v1/host-agent/intent-preview-status":
        return 200, host_agent_intent_preview_status()
    if path in {"/api/v1/strategy-execution", "/api/v1/alerts"}:
        visibility = _strategy_visibility_snapshot()
        if path.endswith("/alerts"):
            return 200, {"status": visibility["status"], "readonly": True,
                         "orders_enabled": False, "alerts": visibility["alerts"],
                         "generated_at": visibility["generated_at"],
                         "control": visibility["control"]}
        return 200, visibility
    if path == "/api/v1/hosts":
        return 200, {
            "status": "ok",
            "profile_ttl_seconds": PROFILE_TTL_SECONDS,
            "hosts": _live_hosts_snapshot(),
        }
    return 404, {"status": "not_found"}


class Handler(BaseHTTPRequestHandler):
    server_version = "BigQMTCoordinator/0.1"

    def do_GET(self) -> None:  # noqa: N802
        split = urlsplit(self.path)
        path = split.path
        if path == "/":
            encoded = coordinator_dashboard_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if path == "/strategies":
            encoded = catalog_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if path == "/api/v1/strategy-deployments":
            query = parse_qs(split.query, keep_blank_values=True)
            host_id = str(query.get("host_id", [""])[0]).strip()
            body = {
                "status": "ok", "readonly": True, "orders_enabled": False,
                "host_id": host_id,
                "deployments": strategy_deployment_store().pending_for_host(host_id),
                "control": "HOST_AGENT_PULL_ONLY_NO_EXECUTION_LEASE",
            }
            code = 200 if host_id else 400
        elif path == "/api/v1/host-agent/intents":
            query = parse_qs(split.query, keep_blank_values=True)
            code, body = host_agent_intent_preview(
                str(query.get("account_id", [""])[0]), str(query.get("host_id", [""])[0])
            )
        else:
            code, body = response_payload(path)
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        post_path = urlsplit(self.path).path
        if post_path == "/api/v1/strategy-install-request":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError("invalid install request size")
                payload = json.loads(self.rfile.read(length))
                code, body = strategy_install_requests(payload)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                code, body = 400, {"status": "rejected", "reason": str(exc),
                                   "readonly": False, "orders_enabled": False}
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if post_path.startswith("/api/v1/strategy-deployments/") and post_path.endswith("/status"):
            deployment_id = post_path[len("/api/v1/strategy-deployments/"):-len("/status")].strip("/")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError("invalid deployment status size")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("deployment status must be an object")
                body = strategy_deployment_store().update_status(
                    deployment_id, str(payload.get("host_id") or ""),
                    str(payload.get("status") or ""), payload.get("result") if isinstance(payload.get("result"), dict) else {},
                )
                code = 200
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                code, body = 400, {"status": "rejected", "reason": str(exc), "orders_enabled": False}
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if urlsplit(self.path).path == "/api/v1/strategy-push-preview":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError("invalid preview request size")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("preview request must be an object")
                body = preview_push(
                    ROOT,
                    str(payload.get("strategy_id", "")),
                    str(payload.get("version", "")),
                    str(payload.get("build_id", "")),
                    payload.get("target_host_ids", []),
                    _live_hosts_snapshot(),
                )
                code = 200
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                code, body = 400, {
                    "status": "rejected",
                    "readonly": True,
                    "orders_enabled": False,
                    "reason": str(exc),
                    "control": "PREVIEW_ONLY_NO_ASSIGNMENT_OR_INSTALL_WRITE",
                }
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if urlsplit(self.path).path == "/api/v1/facts/ingest":
            try:
                ingress = fact_ingress_from_environment()
                if ingress is None:
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2 * 1024 * 1024:
                    raise ValueError("invalid fact request size")
                payload = json.loads(self.rfile.read(length))
                result = ingress.ingest_signed(payload)
                code, body = 202, {
                    "status": result.get("status", "ACCEPTED"),
                    "readonly": True,
                    "orders_enabled": False,
                    "facts_only": True,
                    "accepted": result.get("accepted", []),
                    "duplicates": result.get("duplicates", []),
                }
            except Exception as exc:  # noqa: BLE001 - write path fails closed
                code, body = 400, {
                    "status": "rejected", "readonly": True, "orders_enabled": False,
                    "reason": type(exc).__name__,
                }
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if self.path != "/api/v1/hosts/heartbeat":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            if payload.get("schema_version") != 1 or not payload.get("host_id"):
                raise ValueError("invalid heartbeat")
            if payload.get("state") != "HEALTHY_READONLY":
                raise ValueError("bootstrap accepts readonly heartbeats only")
            if any(key in payload for key in ("password", "secret", "credential", "authorization_key", "orders", "order_intent")):
                raise ValueError("sensitive fields are not accepted")
            account_ids = [ACCOUNT_ALIASES.get(str(value), str(value))
                           for value in payload.get("accounts", []) if str(value).strip()]
            # One Windows host runs one tray per account.  Keep each tray's
            # latest sanitized service report instead of letting the second
            # tray overwrite the first one in the host registry.
            profile_key = account_ids[0] if account_ids else "unbound"
            with HOSTS_LOCK:
                _prune_stale_profiles_locked()
                previous = HOSTS.get(payload["host_id"], {})
                profiles = dict(previous.get("profiles", {}))
                raw_instances = payload.get("strategy_instances", [])
                if not isinstance(raw_instances, list) or len(raw_instances) > 32:
                    raise ValueError("invalid strategy_instances")
                strategy_instances = []
                allowed_instance_fields = {"strategy_id", "version", "state", "policy_enabled",
                                           "authorization_key_state", "bridge_version"}
                for item in raw_instances:
                    if not isinstance(item, dict) or set(item) - allowed_instance_fields:
                        raise ValueError("invalid strategy instance")
                    strategy_id = str(item.get("strategy_id") or "").strip()
                    if not strategy_id or len(strategy_id) > 160:
                        raise ValueError("invalid strategy_id")
                    strategy_state = str(item.get("state") or "UNKNOWN").upper()
                    if strategy_state not in {"RUNNING", "STOPPED", "DEGRADED", "UNKNOWN"}:
                        raise ValueError("invalid strategy state")
                    strategy_instances.append({
                        "strategy_id": strategy_id,
                        "version": str(item.get("version") or "")[:80],
                        "state": strategy_state,
                        "policy_enabled": bool(item.get("policy_enabled", False)),
                        "authorization_key_state": str(item.get("authorization_key_state") or "UNKNOWN").upper()[:32],
                        "bridge_version": str(item.get("bridge_version") or "")[:80],
                    })
                profiles[profile_key] = {
                    "sent_at": payload.get("sent_at"),
                    "services": payload.get("services", {}),
                    "agent_version": payload.get("agent_version", ""),
                    "strategy_instances": strategy_instances,
                }
                all_accounts = sorted(
                    account_id for account_id in profiles if account_id != "unbound"
                )
                record = {
                    "host_id": payload["host_id"],
                    "state": payload["state"],
                    "sent_at": payload.get("sent_at"),
                    "services": payload.get("services", {}),
                    "accounts": all_accounts,
                    "agent_version": payload.get("agent_version", ""),
                    "profiles": profiles,
                }
                HOSTS[payload["host_id"]] = record
            code, body = 202, {"status": "accepted", "mode": "readonly", "host_id": payload["host_id"]}
        except (ValueError, json.JSONDecodeError):
            code, body = 400, {"status": "rejected", "reason": "invalid_readonly_heartbeat"}
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt: str, *args: object) -> None:
        print("coordinator:", fmt % args, flush=True)


def main() -> None:
    """Run exactly one Coordinator process for one local state directory."""
    global COORDINATOR_INSTANCE_ID
    state_dir = Path(os.environ.get("BIGQMT_COORDINATOR_STATE_DIR", str(coordinator_store().database_path.parent)))
    with CoordinatorInstanceLock(state_dir):
        identity = load_or_create_identity(state_dir)
        COORDINATOR_INSTANCE_ID = identity.instance_id
        print(
            f"BigQMT Coordinator mode={COORDINATOR_MODE} instance={identity.instance_id} listening on {HOST}:{PORT}",
            flush=True,
        )
        threading.Thread(target=_profile_reaper, name="profile-reaper", daemon=True).start()
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
