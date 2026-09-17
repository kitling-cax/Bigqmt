"""Single-point machine-local override for BigQMT runtime configuration.

本模块是「唯一本机覆盖文件」的权威实现。契约：

1. 'config/machine.local.json' 只覆盖三类本机变量：
   QMT 根目录、数据目录、端口（Redis / Dashboard / FormulaServer ready port）。
2. 其余配置文件（host_gateway.*.json / tray_profiles.json / data_lake.yaml /
   qmt_paths.yaml）里的路径字段按 project root 相对解析；写相对路径时以数据目录
   （默认 'runtime_data'）或 project root 为基准。
3. 'machine.local.json' 缺失，或某字段缺失时，回退到各配置文件里现在的绝对路径，
   即本机现状行为完全不变（fail-closed，绝不猜测）。

本文件绝不含账户密码；下单授权始终由 strategy_runtime_policy / gateway 控制，
machine.local 不参与下单授权。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:  # qmt_paths.yaml 是可选的辅助配置
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

MACHINE_LOCAL_FILENAME = "machine.local.json"
MACHINE_LOCAL_SCHEMA_FILENAME = "machine.local.schema.json"
SUPPORTED_PROFILES = ("simulation", "production_readonly")

class MachineLocalConfigError(RuntimeError):
    """machine.local.json is present but malformed; runtime entry points must fail closed."""

_BS = chr(92)  # backslash, kept out of source to avoid escaping hazards
_ABSOLUTE_PATH_RE = re.compile(r"[A-Za-z]:[\\/](?!/)[^\"' ]+")
_UNC_PATH_RE = re.compile(re.escape(_BS + _BS) + r"[^\"' ]+")
_PORT_KV_RE = re.compile(r'[A-Za-z_0-9]*port["\']?[ ]*[:=][ ]*["\']?[ ]*([0-9]{2,5})', re.IGNORECASE)
_AUDIT_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".ps1", ".cs", ".md", ".toml", ".cfg", ".ini", ".txt", ".example"}


def project_root() -> Path:
    """Return the repository root (parent of 'src/')."""
    return Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def env_name(profile: str) -> str:
    """Map a tray profile to its gateway/yaml section name."""
    if profile == "simulation":
        return "simulation"
    if profile in ("production", "production_readonly"):
        return "production_readonly"
    raise ValueError("unsupported profile: %s" % profile)


def load_machine_local(root: Path | None = None) -> dict[str, Any]:
    """Read the machine-local override file.

    A missing file is the supported fallback (empty dict). A present but
    malformed file hard-fails as MachineLocalConfigError so runtime entry
    points cannot silently run against an unknown local override.
    """
    root = Path(root) if root else project_root()
    path = root / "config" / MACHINE_LOCAL_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MachineLocalConfigError(
            "machine.local.json is not a valid JSON file: %s" % exc
        ) from exc
    if not isinstance(data, dict):
        raise MachineLocalConfigError("machine.local.json must be a JSON object")
    return data


def machine_environment(machine: dict[str, Any], profile: str) -> dict[str, Any]:
    envs = machine.get("environments") if isinstance(machine.get("environments"), dict) else {}
    node = envs.get(env_name(profile))
    return node if isinstance(node, dict) else {}


def resolve_preset_path(value: Any, root: Path) -> Path:
    """Resolve an explicit local path against project root when relative."""
    path = Path(str(value))
    if path.is_absolute():
        return path.resolve()
    return (Path(root) / path).resolve()


def config_data_directory(configured: Any, root: Path) -> Path:
    """Resolve a machine-local 'data_directory' value (may be relative)."""
    return resolve_preset_path(configured, root)


def runtime_data_directory(root: Path) -> Path:
    """Resolve the effective runtime-data root (honours data_directory override)."""
    machine = load_machine_local(root)
    configured = machine.get("data_directory")
    if configured:
        return config_data_directory(configured, root)
    return (root / "runtime_data").resolve()


def _resolve_runtime_path(root: Path, value: Any) -> str:
    """Resolve a gateway path field with single-point data-directory override.

    - 无 'data_directory' 覆盖：相对路径相对默认 runtime_data 解析，绝对路径原样，
      即缺省回退到现在的绝对路径。
    - 有 'data_directory' 覆盖：绝对路径若位于默认 runtime_data 之下，则把该前缀
      重定位到新数据目录；相对路径相对新数据目录解析。
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    default_data = (root / "runtime_data").resolve()
    machine = load_machine_local(root)
    configured = machine.get("data_directory")
    if not configured:
        if path.is_absolute():
            return str(path.resolve())
        return str((default_data / path).resolve())
    new_root = config_data_directory(configured, root)
    if path.is_absolute():
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(default_data)
        except ValueError:
            return str(resolved)
        return str((new_root / relative).resolve())
    return str((new_root / path).resolve())


def apply_gateway_overrides(root: Path, profile: str, gateway: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the gateway config with machine-local overrides applied.

    仅覆盖 Redis 端点与 state_db/audit_dir 的本地定位；不触碰账户、下单开关。
    """
    out = dict(gateway)
    machine = load_machine_local(root)
    env = machine_environment(machine, profile)
    redis_override = env.get("redis")
    if isinstance(redis_override, dict) and redis_override:
        merged = dict(out.get("redis") or {})
        for key in ("host", "port", "db", "password"):
            value = redis_override.get(key)
            if value not in (None, ""):
                merged[key] = value
        out["redis"] = merged
    for key in ("state_db", "audit_dir"):
        if out.get(key):
            out[key] = _resolve_runtime_path(root, out[key])
    return out


def load_gateway(root: Path, profile: str) -> dict[str, Any]:
    """Authoritative gateway loader: file + machine-local overrides."""
    root = Path(root)
    path = root / "config" / ("host_gateway.%s.json" % env_name(profile))
    gateway = load_json(path)
    return apply_gateway_overrides(root, profile, gateway)


def load_tray_profiles(root: Path) -> dict[str, Any]:
    """Authoritative tray_profiles loader with machine-local overrides."""
    root = Path(root)
    data = load_json(root / "config" / "tray_profiles.json")
    machine = load_machine_local(root)
    profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
    for profile in SUPPORTED_PROFILES:
        entry = profiles.get(profile)
        if not isinstance(entry, dict):
            continue
        env = machine_environment(machine, profile)
        if env.get("qmt_root"):
            entry["qmt_root"] = str(resolve_preset_path(env["qmt_root"], root))
        redis_override = env.get("redis")
        if isinstance(redis_override, dict) and redis_override:
            merged = dict(entry.get("redis") or {})
            for key in ("host", "port", "db", "password"):
                value = redis_override.get(key)
                if value not in (None, ""):
                    merged[key] = value
            entry["redis"] = merged
        if env.get("dashboard_port"):
            dash = dict(entry.get("dashboard") or {})
            dash["port"] = int(env["dashboard_port"])
            entry["dashboard"] = dash
        if env.get("ready_port"):
            launch = dict(entry.get("qmt_launch") or {})
            launch["ready_port"] = int(env["ready_port"])
            entry["qmt_launch"] = launch
    data["profiles"] = profiles
    return data


def load_qmt_paths(root: Path) -> dict[str, Any]:
    """Optional qmt_paths.yaml loader with machine-local overrides (PyYAML optional)."""
    root = Path(root)
    if yaml is None:
        return {}
    path = root / "config" / "qmt_paths.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(data, dict):
        return {}
    machine = load_machine_local(root)
    section_map = {"simulation": "simulation", "production_readonly": "production"}
    for profile, section in section_map.items():
        env = machine_environment(machine, profile)
        node = data.get(section)
        if not isinstance(node, dict):
            continue
        if env.get("qmt_root"):
            node["install_root"] = str(resolve_preset_path(env["qmt_root"], root))
        if env.get("bin_x64"):
            node["bin_x64"] = str(resolve_preset_path(env["bin_x64"], root))
        elif env.get("qmt_root"):
            node["bin_x64"] = str(resolve_preset_path(env["qmt_root"], root) / "bin.x64")
    return data


def apply_data_lake_root(root: Path, lake_root: Any) -> str:
    """Resolve a data-lake root value (absolute stays, relative under data dir)."""
    raw = str(lake_root or "").strip()
    if not raw:
        return str(runtime_data_directory(root) / "lake")
    path = Path(raw)
    if path.is_absolute():
        return str(path.resolve())
    return str((runtime_data_directory(root) / path).resolve())


def load_machine_local_schema(root: Path | None = None) -> dict[str, Any]:
    """Load the JSON Schema for machine.local.json (missing/invalid yields {})."""
    root = Path(root) if root else project_root()
    return load_json(root / "config" / "schemas" / MACHINE_LOCAL_SCHEMA_FILENAME)


def validate_machine_local(root: Path | None = None) -> list[str]:
    """Validate config/machine.local.json against its JSON Schema (fail-closed).

    Missing override file is a supported fallback (returns []). An unreadable,
    " non-object, or schema-invalid file returns one or more human-readable errors.
    """
    root = Path(root) if root else project_root()
    schema = load_machine_local_schema(root)
    if not schema:
        return ["machine.local.json schema is missing or not a valid JSON object"]
    path = root / "config" / MACHINE_LOCAL_FILENAME
    if not path.exists():
        return []
    try:
        machine = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ["machine.local.json is not a valid JSON file: %s" % exc]
    if not isinstance(machine, dict):
        return ["machine.local.json must be a JSON object"]
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema is not installed"]
    errors: list[str] = []
    validator = jsonschema.Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(machine), key=lambda e: tuple(str(p) for p in e.absolute_path)):
        location = "$" + "".join(
            "[%d]" % p if isinstance(p, int) else ".%s" % p for p in err.absolute_path
        ) if list(err.absolute_path) else "$"
        errors.append("%s: %s" % (location, err.message))
    return errors


def effective_config(root: Path | None = None, profile: str = "simulation") -> dict[str, Any]:
    """Render one profile's effective paths and endpoints after local override.

    This is the single-source projection used to prove every entry point
    " resolves the same machine-local values. It is deterministic and secret-free.
    """
    root = Path(root) if root else project_root()
    env = env_name(profile)
    gateway = load_gateway(root, profile)
    profiles = load_tray_profiles(root).get("profiles") or {}
    tray = profiles.get(profile) or {}
    env_local = machine_environment(load_machine_local(root), profile)
    data_dir = runtime_data_directory(root)

    qmt_root = str(tray.get("qmt_root") or env_local.get("qmt_root") or "")
    bin_x64 = str(env_local.get("bin_x64") or "")
    if not bin_x64 and qmt_root:
        bin_x64 = str(Path(qmt_root) / "bin.x64")

    dashboard = tray.get("dashboard")
    dashboard_port = dashboard.get("port") if isinstance(dashboard, dict) else None
    launch = tray.get("qmt_launch")
    ready_port = launch.get("ready_port") if isinstance(launch, dict) else None

    redis = gateway.get("redis") or {}
    redis_out = {key: redis[key] for key in ("host", "port", "db") if key in redis}

    from kitling_bigqmt.coordinator_endpoint import resolve_coordinator
    endpoint, host_id = resolve_coordinator(root)

    return {
        "profile": profile,
        "environment": env,
        "data_directory": str(data_dir),
        "coordinator": {"endpoint": endpoint, "host_id": host_id},
        "qmt_root": qmt_root,
        "bin_x64": bin_x64,
        "redis": redis_out,
        "state_db": gateway.get("state_db") or "",
        "audit_dir": gateway.get("audit_dir") or "",
        "dashboard_port": dashboard_port,
        "ready_port": ready_port,
        "orders_enabled": bool(tray.get("orders_enabled")),
    }


def effective_config_hash(root: Path | None = None, profile: str = "simulation") -> str:
    """Return a stable SHA-256 over the deterministic effective config."""
    payload = effective_config(root, profile)
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def audit_hardcoded_paths(root: Path | None = None) -> dict[str, Any]:
    """Inventory absolute local paths and port literals in config/scripts/src.

    Read-only; returns a structured findings report suitable for the audit trail.
    """
    root = Path(root) if root else project_root()
    scanners = ["config", "scripts", "src"]
    findings: list[dict[str, Any]] = []
    scanned: list[str] = []
    for rel_dir in scanners:
        base = root / rel_dir
        if not base.is_dir():
            continue
        scanned.append(rel_dir)
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _AUDIT_SUFFIXES:
                continue
            try:
                text_content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = path.relative_to(root).as_posix()
            for lineno, line in enumerate(text_content.splitlines(), 1):
                for match in _ABSOLUTE_PATH_RE.finditer(line):
                    findings.append({"file": rel, "line": lineno, "kind": "absolute_path", "value": match.group(0)})
                for match in _UNC_PATH_RE.finditer(line):
                    findings.append({"file": rel, "line": lineno, "kind": "unc_path", "value": match.group(0)})
                for match in _PORT_KV_RE.finditer(line):
                    findings.append({"file": rel, "line": lineno, "kind": "port", "value": match.group(1)})
    return {"scanned": scanned, "finding_count": len(findings), "findings": findings}
