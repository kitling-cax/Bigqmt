"""Build a deterministic candidate bundle for the BigQMT read-only MCP/Skill."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0-readonly"
FILES = {
    "openclaw/bigqmt-operator/SKILL.md": "skill/SKILL.md",
    "openclaw/bigqmt-operator/mcp.server.example.json": "mcp/server.example.json",
    "scripts/openclaw_bigqmt_readonly_mcp.py": "project_overlay/scripts/openclaw_bigqmt_readonly_mcp.py",
    "src/kitling_bigqmt/openclaw_readonly_gateway.py": "project_overlay/src/kitling_bigqmt/openclaw_readonly_gateway.py",
    "src/kitling_bigqmt/coordinator_endpoint.py": "project_overlay/src/kitling_bigqmt/coordinator_endpoint.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError("refusing to overwrite immutable bundle: %s" % destination)
    destination.mkdir(parents=True)
    entries = []
    for source_rel, target_rel in FILES.items():
        source = ROOT / source_rel
        target = destination / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        entries.append({"path": target_rel.replace("\\", "/"), "sha256": sha256(target), "bytes": target.stat().st_size})
    readme = destination / "README_INSTALL.md"
    readme.write_text(
        "# BigQMT OpenClaw 只读候选包\n\n"
        "本包只包含 fleet、executor preview、project progress 查询。它不含 token、凭据、确认、租约写入或下单能力。\n\n"
        "先在目标机本地复制并校验 manifest；不要从 NAS 共享目录直接运行。"
        "将 `project_overlay` 合并到该目标机的本地 BigQMT 项目后，使用 `mcp/server.example.json` 注册 stdio 命令。"
        "实际 OpenClaw 配置路径与 Agent 身份仍需在 AP4 时确认。\n",
        encoding="utf-8",
    )
    entries.append({"path": "README_INSTALL.md", "sha256": sha256(readme), "bytes": readme.stat().st_size})
    manifest = {
        "schema_version": 1,
        "release": "openclaw-bigqmt-bundle-" + VERSION,
        "channel": "candidate",
        "scope": "observer_readonly",
        "orders_enabled": False,
        "requires": {"python": "3.12", "coordinator_endpoint": "machine.local.json or BIGQMT_COORDINATOR_ENDPOINT"},
        "files": entries,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksums = "\n".join("%s  %s" % (item["sha256"], item["path"]) for item in entries) + "\n"
    (destination / "checksums.sha256").write_text(checksums, encoding="utf-8")
    return manifest


if __name__ == "__main__":
    output = ROOT / "dist" / ("openclaw-bigqmt-bundle-" + VERSION)
    print(json.dumps(build(output), ensure_ascii=False, indent=2))
