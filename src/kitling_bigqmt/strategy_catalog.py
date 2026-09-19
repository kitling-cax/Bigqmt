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


def catalog_html() -> str:
    """Small dependency-free read-only strategy catalog page."""
    return """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>BigQMT 策略库</title>
<style>body{margin:0;background:#f5f7fb;color:#172033;font:14px 'Segoe UI','Microsoft YaHei',sans-serif}.wrap{max-width:1180px;margin:auto;padding:28px}.card{background:#fff;border:1px solid #e1e7ef;border-radius:12px;padding:20px;margin:14px 0;box-shadow:0 2px 8px #1e293b0a}h1{margin:0 0 6px}.muted{color:#64748b}.tag{display:inline-block;border-radius:999px;padding:5px 9px;margin:4px 4px 0 0;font-size:12px;background:#ecfdf3;color:#157a50}.lock{background:#fff7e5;color:#925d00}.row{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:12px;margin-top:15px}.cell{border:1px solid #e4e9f0;border-radius:8px;padding:10px;word-break:break-word}@media(max-width:720px){.row{grid-template-columns:1fr}}</style></head>
<body><main class='wrap'><div class='card'><h1>BigQMT 私有策略库</h1><div class='muted'>候选版本只读浏览 · 策略源码不进入 GitHub</div><div id='summary' class='muted'>读取中…</div></div><div id='list'></div></main>
<script>async function load(){const root=document.getElementById('list'),summary=document.getElementById('summary');try{const r=await fetch('/api/v1/strategy-candidates',{cache:'no-store'});if(!r.ok)throw Error();const d=await r.json();summary.textContent=(d.library_available?'策略库在线':'策略库不可用')+' · '+(d.candidates||[]).length+' 个 candidate · 当前不支持网页推送';root.replaceChildren();for(const x of d.candidates||[]){const c=document.createElement('section');c.className='card';const h=document.createElement('h2');h.textContent=x.strategy_id||'未知策略';c.append(h);const row=document.createElement('div');row.className='row';for(const v of [x.version||'-',x.build_id||'-',x.status||'-',x.manifest_sha256||'-']){const cell=document.createElement('div');cell.className='cell';cell.textContent=v;row.append(cell)}c.append(row);const safe=document.createElement('div');safe.innerHTML='<span class="tag">orders_enabled=false</span><span class="tag">formal_account_allowed=false</span><span class="tag lock">推送/安装：待实现</span>';c.append(safe);root.append(c)}}catch(e){summary.textContent='策略库读取失败';root.textContent='Coordinator 暂不可达'}}load();setInterval(load,10000)</script></body></html>"""
