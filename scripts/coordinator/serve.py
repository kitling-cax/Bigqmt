"""Read-only Coordinator bootstrap service.

Only health/readiness/progress endpoints are exposed in this milestone.  No
QMT, Redis, order, shell, or OpenClaw integration is imported here.
"""
from __future__ import annotations

import json
import os
import sys
import threading
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

HOST = os.environ.get("BIGQMT_COORDINATOR_BIND", "127.0.0.1")
PORT = int(os.environ.get("BIGQMT_COORDINATOR_PORT", "18443"))
COORDINATOR_MODE = os.environ.get("BIGQMT_COORDINATOR_MODE", "READONLY_FOUNDATION").strip().upper()
COORDINATOR_INSTANCE_ID = os.environ.get("BIGQMT_COORDINATOR_INSTANCE_ID", "UNINITIALIZED")
HOSTS: dict[str, dict] = {}
HOSTS_LOCK = threading.Lock()
ACCOUNT_POLICY = {
    "90000001": {"mode": "SIMULATION", "execution_eligible": True},
    "90000002": {"mode": "PRODUCTION_READ_ONLY", "execution_eligible": False},
}
REQUIRED_EXECUTOR_SERVICES = ("qmt", "redis", "bridge", "tray")


def coordinator_store() -> CoordinatorStore:
    """Obtain the durable lease store without exposing a write HTTP API."""
    default = "/var/lib/kitling-bigqmt-coordinator/coordinator.sqlite3"
    if os.name == "nt":
        default = str(ROOT / "runtime_data" / "coordinator" / "coordinator.sqlite3")
    return CoordinatorStore(os.environ.get("BIGQMT_COORDINATOR_DB", default))


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


def _heartbeat_age_seconds(sent_at: object) -> int | None:
    try:
        value = datetime.fromisoformat(str(sent_at).replace("Z", "+00:00"))
        return max(0, int((datetime.now(timezone.utc) - value).total_seconds()))
    except (TypeError, ValueError):
        return None


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
    with HOSTS_LOCK:
        hosts = list(HOSTS.values())
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
    return {"status": "ok", "mode": "readonly-preview", "accounts": entries}


def host_agent_intent_preview(account_id: str, host_id: str) -> tuple[int, dict]:
    """Return a deliberately empty, non-executable Host Agent inbox.

    This endpoint is the first M03 connectivity seam only.  It never reads
    Coordinator intents, leases, QMT, Redis, or any broker state.  A future
    order-intent rollout requires a distinct authorized endpoint and contract.
    """
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
    with HOSTS_LOCK:
        hosts = list(HOSTS.values())
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
        "orders_enabled": False, "targets": targets,
        "control": "EMPTY_PREVIEW_NO_INTENT_READ_OR_EXECUTION",
    }


def coordinator_dashboard_html() -> str:
    """Small dependency-free, read-only Coordinator monitor page."""
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BigQMT Coordinator</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#172033;font:14px "Segoe UI","Microsoft YaHei",sans-serif}.top{background:#fff;border-bottom:1px solid #e4e9f0;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;gap:16px}.brand{font-size:20px;font-weight:700}.sub{color:#64748b;margin-top:4px}.chip{border:1px solid #b9ddc9;background:#edfbf2;color:#147a50;border-radius:999px;padding:6px 10px;font-size:12px}main{max-width:1240px;margin:0 auto;padding:24px}.summary{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:14px;margin-bottom:18px}.metric,.host{background:#fff;border:1px solid #e1e7ef;border-radius:12px;box-shadow:0 2px 8px rgba(30,41,59,.04)}.metric{padding:16px}.label{font-size:12px;color:#64748b}.value{font-size:24px;font-weight:700;margin-top:8px}.host{padding:18px;margin-top:14px}.hosthead{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.hostid{font-size:17px;font-weight:700}.note{color:#64748b;font-size:12px;margin-top:5px}.mode{background:#fff7e5;border:1px solid #f1d398;color:#925d00;border-radius:999px;padding:5px 9px;font-size:12px;white-space:nowrap}.profiles{display:grid;grid-template-columns:repeat(2,minmax(270px,1fr));gap:12px;margin-top:16px}.profile{border:1px solid #e4e9f0;border-radius:10px;padding:14px}.profile h3{font-size:14px;margin:0 0 10px}.services{display:flex;flex-wrap:wrap;gap:7px}.service{font-size:12px;border-radius:6px;padding:5px 7px;background:#f1f5f9;color:#475569}.service.up{background:#ecfdf3;color:#157a50}.service.down{background:#fff1f2;color:#b42318}.empty{padding:38px;text-align:center;color:#64748b;background:#fff;border:1px dashed #cbd5e1;border-radius:12px}.foot{margin-top:18px;color:#64748b;font-size:12px}@media(max-width:700px){.top{padding:15px 18px}.summary,.profiles{grid-template-columns:1fr}main{padding:16px}}
</style></head><body><header class="top"><div><div class="brand">BigQMT Coordinator</div><div class="sub">多主机托盘与账户状态 · 只读监控</div></div><div class="chip">订单控制未开放</div></header><main><section class="summary"><div class="metric"><div class="label">在线主机</div><div class="value" id="hostCount">—</div></div><div class="metric"><div class="label">已上报账户</div><div class="value" id="accountCount">—</div></div><div class="metric"><div class="label">ACTIVE_EXECUTOR</div><div class="value" id="executor">未分配</div></div><div class="metric"><div class="label">Intent Preview</div><div class="value" id="intentPreview">—</div></div></section><div id="hosts" class="empty">正在读取 Coordinator 状态…</div><div class="foot">每 30 秒由账户托盘发送脱敏只读心跳。页面每 10 秒刷新；不含凭据、订单或策略控制。</div></main><script>
const labels={qmt:'QMT',miniqmt:'MiniQMT',redis:'Redis',bridge:'Bridge',dashboard:'Dashboard',tray:'Tray'};
function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function render(data){const hosts=Array.isArray(data.hosts)?data.hosts:[];document.getElementById('hostCount').textContent=hosts.length;const accounts=new Set(hosts.flatMap(h=>h.accounts||[]));document.getElementById('accountCount').textContent=accounts.size;const root=document.getElementById('hosts');root.replaceChildren();if(!hosts.length){root.className='empty';root.textContent='尚未收到任何托盘心跳';return}root.className='';for(const host of hosts){const card=node('section','host');const head=node('div','hosthead');const title=node('div');title.append(node('div','hostid',host.host_id),node('div','note','最后心跳：'+(host.sent_at||'—')+' · '+(host.state||'UNKNOWN')));head.append(title,node('span','mode','只读监控'));card.append(head);const profiles=host.profiles||{};const grid=node('div','profiles');for(const account of Object.keys(profiles).sort()){const report=profiles[account]||{};const box=node('article','profile');box.append(node('h3','',account));const services=node('div','services');for(const key of Object.keys(labels)){const value=(report.services||{})[key]||'UNKNOWN';services.append(node('span','service '+value.toLowerCase(),labels[key]+' '+value));}box.append(services, node('div','note','更新时间：'+(report.sent_at||'—')));grid.append(box)}card.append(grid);root.append(card)}}
async function refresh(){try{const [h,e,i]=await Promise.all([fetch('/api/v1/hosts',{cache:'no-store'}),fetch('/api/v1/executor-preview',{cache:'no-store'}),fetch('/api/v1/host-agent/intent-preview-status',{cache:'no-store'})]);if(!h.ok||!e.ok||!i.ok)throw Error();const hosts=await h.json(),preview=await e.json(),intents=await i.json();const eligible=(preview.accounts||[]).flatMap(a=>a.candidates||[]).filter(c=>c.eligible).length;document.getElementById('executor').textContent=eligible?'未分配（'+eligible+' 候选）':'未分配';document.getElementById('intentPreview').textContent=(intents.orders_enabled===false?'空队列／只读':'异常');render(hosts)}catch{document.getElementById('hosts').className='empty';document.getElementById('hosts').textContent='Coordinator 暂不可达'}}refresh();setInterval(refresh,10000);
</script></body></html>"""


def response_payload(path: str) -> tuple[int, dict]:
    if path == "/healthz":
        return 200, {"status": "ok", "service": "kitling-bigqmt-coordinator", "mode": COORDINATOR_MODE.lower()}
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
    if path == "/api/v1/executor-preview":
        return 200, executor_preview()
    if path == "/api/v1/fleet":
        return 200, {
            "status": "ok",
            "mode": "readonly-fleet",
            "readonly": True,
            "orders_enabled": False,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hosts": list(HOSTS.values()),
            "executor_preview": executor_preview(),
            "intent_preview": host_agent_intent_preview_status(),
            "progress": load_progress(),
            "control": "READ_ONLY_FLEET_PROJECTION",
        }
    if path == "/api/v1/host-agent/intent-preview-status":
        return 200, host_agent_intent_preview_status()
    if path == "/api/v1/hosts":
        with HOSTS_LOCK:
            return 200, {"status": "ok", "hosts": list(HOSTS.values())}
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
        if path == "/api/v1/host-agent/intents":
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
            if any(key in payload for key in ("password", "orders", "order_intent")):
                raise ValueError("sensitive fields are not accepted")
            account_ids = [str(value) for value in payload.get("accounts", []) if str(value).strip()]
            # One Windows host runs one tray per account.  Keep each tray's
            # latest sanitized service report instead of letting the second
            # tray overwrite the first one in the host registry.
            profile_key = account_ids[0] if account_ids else "unbound"
            with HOSTS_LOCK:
                previous = HOSTS.get(payload["host_id"], {})
                profiles = dict(previous.get("profiles", {}))
                profiles[profile_key] = {
                    "sent_at": payload.get("sent_at"),
                    "services": payload.get("services", {}),
                    "agent_version": payload.get("agent_version", ""),
                }
                all_accounts = sorted(set(previous.get("accounts", [])) | set(account_ids))
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
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
