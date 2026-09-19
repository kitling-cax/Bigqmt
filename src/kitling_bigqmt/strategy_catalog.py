"""Read-only scanner for immutable private strategy packages."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def library_root(project_root: Path) -> Path:
    configured = os.environ.get("BIGQMT_STRATEGY_LIBRARY_ROOT", "").strip()
    if configured:
        return Path(configured)
    if os.name == "nt":
        return project_root / "releases" / "strategies"
    return Path("/var/lib/kitling-bigqmt-coordinator/strategy-library")


def _scan_manifest(path: Path, root: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        required = ("strategy_id", "version", "build_id", "artifacts", "safety")
        if any(not manifest.get(key) for key in required):
            raise ValueError("manifest missing required fields")
        safety = manifest.get("safety") or {}
        if safety.get("orders_enabled") is not False or safety.get("formal_account_allowed") is not False:
            raise ValueError("unsafe package flags")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("manifest artifacts are empty")
        checked = 0
        for item in artifacts:
            rel = Path(str(item.get("path") or ""))
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("unsafe artifact path")
            artifact = path.parent / rel
            if not artifact.is_file() or _sha256(artifact).lower() != str(item.get("sha256") or "").lower():
                raise ValueError(f"artifact checksum mismatch: {rel.as_posix()}")
            checked += 1
        return {
            "strategy_id": str(manifest["strategy_id"]),
            "version": str(manifest["version"]),
            "build_id": str(manifest["build_id"]),
            "bridge_rpc_version": str(manifest.get("bridge_rpc_version") or ""),
            "artifact_count": checked,
            "manifest_sha256": _sha256(path),
            "package_path": path.parent.relative_to(root).as_posix(),
            "status": "READY",
            "orders_enabled": False,
            "formal_account_allowed": False,
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"package_path": path.parent.relative_to(root).as_posix(), "status": "INVALID",
                "reason": str(exc), "orders_enabled": False, "formal_account_allowed": False}


def list_candidates(project_root: Path) -> dict[str, Any]:
    root = library_root(project_root)
    entries: list[dict[str, Any]] = []
    if root.is_dir():
        for manifest in sorted(root.rglob("MANIFEST.json")):
            if manifest.is_symlink():
                continue
            entries.append(_scan_manifest(manifest, root))
    return {
        "status": "ok", "readonly": True, "orders_enabled": False,
        "library_available": root.is_dir(), "library_root": str(root),
        "candidates": entries, "push_supported": False, "install_supported": False,
        "control": "CATALOG_ONLY_NO_INSTALL_OR_ASSIGNMENT_WRITE",
    }


def preview_push(
    project_root: Path,
    strategy_id: str,
    version: str,
    build_id: str,
    target_host_ids: list[str],
    live_hosts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate a candidate/target selection without writing any state.

    This is deliberately a *preview* contract.  It does not create an
    assignment, lease, outbox item, install request, or execution permission.
    A future Host Agent pull/install flow must be a separate, authenticated
    write contract with its own approval gate.
    """
    if not all(isinstance(value, str) and value.strip() for value in
               (strategy_id, version, build_id)):
        raise ValueError("strategy_id, version and build_id are required")
    if not isinstance(target_host_ids, list) or not target_host_ids:
        raise ValueError("at least one target_host_id is required")
    normalized_targets: list[str] = []
    for value in target_host_ids:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("target_host_ids must contain non-empty strings")
        value = value.strip()
        if value not in normalized_targets:
            normalized_targets.append(value)
    if len(normalized_targets) > 32:
        raise ValueError("too many target hosts")

    catalog = list_candidates(project_root)
    candidate = next(
        (
            item for item in catalog["candidates"]
            if item.get("strategy_id") == strategy_id
            and item.get("version") == version
            and item.get("build_id") == build_id
        ),
        None,
    )
    if candidate is None:
        raise ValueError("strategy candidate not found")
    if candidate.get("status") != "READY":
        raise ValueError("strategy candidate is not READY")

    connected = {
        str(host.get("host_id")): host
        for host in live_hosts
        if isinstance(host, dict) and str(host.get("host_id") or "").strip()
    }
    targets = []
    for host_id in normalized_targets:
        host = connected.get(host_id)
        targets.append({
            "host_id": host_id,
            "status": "READY_TO_PULL" if host else "HOST_NOT_CONNECTED",
            "host_state": host.get("state") if host else None,
            "last_heartbeat": host.get("sent_at") if host else None,
            "would_write": False,
            "install_started": False,
            "orders_enabled": False,
        })
    return {
        "status": "PREVIEW_ONLY",
        "readonly": True,
        "orders_enabled": False,
        "strategy": {
            "strategy_id": candidate["strategy_id"],
            "version": candidate["version"],
            "build_id": candidate["build_id"],
            "manifest_sha256": candidate["manifest_sha256"],
            "artifact_count": candidate["artifact_count"],
        },
        "targets": targets,
        "assignment_created": False,
        "install_started": False,
        "lease_created": False,
        "control": "PREVIEW_ONLY_NO_ASSIGNMENT_OR_INSTALL_WRITE",
        "warning": "同一策略可以安装到多个主机，但同一账户同时只能有一个 ACTIVE_EXECUTOR。",
    }


def catalog_html() -> str:
    """Small dependency-free strategy catalog and push-preview page."""
    return """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>BigQMT 策略库</title>
<style>body{margin:0;background:#f5f7fb;color:#172033;font:14px 'Segoe UI','Microsoft YaHei',sans-serif}.wrap{max-width:1180px;margin:auto;padding:28px}.card{background:#fff;border:1px solid #e1e7ef;border-radius:12px;padding:20px;margin:14px 0;box-shadow:0 2px 8px #1e293b0a}h1{margin:0 0 6px}.muted{color:#64748b}.tag{display:inline-block;border-radius:999px;padding:5px 9px;margin:4px 4px 0 0;font-size:12px;background:#ecfdf3;color:#157a50}.lock{background:#fff7e5;color:#925d00}.row{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:12px;margin-top:15px}.cell{border:1px solid #e4e9f0;border-radius:8px;padding:10px;word-break:break-word}.targets{border-top:1px solid #edf0f4;margin-top:18px;padding-top:14px}.target{display:inline-flex;align-items:center;gap:6px;border:1px solid #dbe3ec;border-radius:8px;padding:8px 10px;margin:4px 6px 4px 0;background:#fbfdff}.target input{accent-color:#2563eb}.button{border:0;border-radius:8px;padding:9px 14px;background:#2563eb;color:#fff;cursor:pointer;margin-top:10px}.button:disabled{background:#94a3b8;cursor:not-allowed}.preview{margin-top:12px;padding:12px;border-radius:8px;background:#f8fafc;white-space:pre-wrap}.ok{color:#157a50}.warn{color:#925d00}@media(max-width:720px){.row{grid-template-columns:1fr}}</style></head>
<body><main class='wrap'><div class='card'><h1>BigQMT 私有策略库</h1><div class='muted'>候选版本来自 NAS 私有库 · 策略源码不进入 GitHub</div><div id='summary' class='muted'>读取中…</div></div><div id='list'></div></main>
<script>const root=document.getElementById('list'),summary=document.getElementById('summary');let hosts=[];
function compactHost(id){const m=String(id||'').match(/(?:^|[.])((?:10|192|172)[.][0-9.]+)$/);return m?'.'+String(id).split('.').pop():String(id||'未知主机')}
async function load(){try{const [cr,hr]=await Promise.all([fetch('/api/v1/strategy-candidates',{cache:'no-store'}),fetch('/api/v1/hosts',{cache:'no-store'})]);if(!cr.ok||!hr.ok)throw Error();const d=await cr.json(),hd=await hr.json();hosts=Array.isArray(hd.hosts)?hd.hosts:[];summary.textContent=(d.library_available?'策略库在线':'策略库不可用')+' · '+(d.candidates||[]).length+' 个 candidate · 已支持推送预览（不写入）';root.replaceChildren();for(const x of d.candidates||[]){const c=document.createElement('section');c.className='card';const h=document.createElement('h2');h.textContent=x.strategy_id||'未知策略';c.append(h);const row=document.createElement('div');row.className='row';for(const v of [x.version||'-',x.build_id||'-',x.status||'-',x.manifest_sha256||'-']){const cell=document.createElement('div');cell.className='cell';cell.textContent=v;row.append(cell)}c.append(row);const safe=document.createElement('div');safe.innerHTML='<span class="tag">orders_enabled=false</span><span class="tag">formal_account_allowed=false</span><span class="tag lock">当前动作：只读推送预览</span>';c.append(safe);const section=document.createElement('div');section.className='targets';const title=document.createElement('div');title.className='muted';title.textContent='选择目标托盘（仅生成预览，不安装、不创建租约）';section.append(title);if(!hosts.length){const empty=document.createElement('div');empty.className='muted';empty.textContent='暂无在线托盘心跳';section.append(empty)}else{for(const host of hosts){const label=document.createElement('label');label.className='target';const input=document.createElement('input');input.type='checkbox';input.value=host.host_id||'';input.dataset.hostId=host.host_id||'';const text=document.createElement('span');text.textContent=compactHost(host.host_id)+' · '+(host.state||'UNKNOWN');label.append(input,text);section.append(label)}}const button=document.createElement('button');button.className='button';button.textContent='生成推送预览';button.onclick=async()=>{button.disabled=true;const selected=[...section.querySelectorAll('input:checked')].map(e=>e.value);const box=section.querySelector('.preview')||document.createElement('div');box.className='preview';section.append(box);try{const response=await fetch('/api/v1/strategy-push-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({strategy_id:x.strategy_id,version:x.version,build_id:x.build_id,target_host_ids:selected})});const data=await response.json();box.textContent=JSON.stringify(data,null,2);box.classList.toggle('ok',response.ok);box.classList.toggle('warn',!response.ok)}catch(e){box.textContent='预览请求失败：Coordinator 不可达';box.className='preview warn'}finally{button.disabled=false}};section.append(button);c.append(section);root.append(c)}}catch(e){summary.textContent='策略库读取失败';root.textContent='Coordinator 暂不可达'}}load();setInterval(load,10000)</script></body></html>"""
