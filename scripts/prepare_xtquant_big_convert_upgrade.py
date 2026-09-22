"""Prepare a fail-closed BigQMT bridge candidate from an upstream checkout.

The upstream project owns the transport, read-path and QMT compatibility code.
This project owns the final execution boundary: local account identity,
authorization and strategy-attributed cancellation.  An upgrade must retain
both layers.  The script deliberately refuses an unknown upstream layout
instead of silently emitting a bridge without the local protections.
"""

from __future__ import annotations

import argparse
import compileall
import hashlib
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_PACKAGE = ROOT / "staging" / "qmt_bridge_simulation" / "bigqmt_signal_trader"
SAFEGUARD_FILES = (
    Path("execution_admission.py"),
    Path("adapters") / "order_guarded.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError("%s anchor count is %s, expected exactly 1" % (label, count))
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def install_local_execution_boundary(package: Path) -> None:
    adapter_factory = package / "adapter_factory.py"
    replace_once(
        adapter_factory,
        '    if mode == "bigqmt":\n        from .adapters.market_bigqmt import BigQmtMarketDataProvider\n        from .adapters.order_bigqmt import BigQmtOrderGateway\n',
        '    if mode == "bigqmt":\n        from .execution_admission import OrderAdmissionPolicy\n        from .adapters.market_bigqmt import BigQmtMarketDataProvider\n        from .adapters.order_bigqmt import BigQmtOrderGateway\n        from .adapters.order_guarded import GuardedOrderGateway\n',
        "adapter imports",
    )
    replace_once(
        adapter_factory,
        '            quick_trade=int(config.get("quick_trade", 2)),\n        )\n\n    return SignalTradingApp(\n',
        '            quick_trade=int(config.get("quick_trade", 2)),\n        )\n        # Upstream stays broker-capable; the local wrapper makes every write\n        # account-bound, locally authorized and strategy-attributed.\n        order_gateway = GuardedOrderGateway(\n            order_gateway,\n            OrderAdmissionPolicy(config.get("execution_admission"), account_id),\n        )\n\n    return SignalTradingApp(\n',
        "adapter execution boundary",
    )

    rpc = package / "redis_rpc.py"
    replace_once(
        rpc,
        '        self.position_sync_sink = position_sync_sink\n        self.allow_order_methods = bool(allow_order_methods)\n        self.quote_subscription_manager = quote_subscription_manager\n',
        '        self.position_sync_sink = position_sync_sink\n        self.allow_order_methods = bool(allow_order_methods)\n        # Keep the policy at the RPC entry as a second, independent guard.\n        self.order_admission = getattr(order_gateway, "admission", None)\n        self.quote_subscription_manager = quote_subscription_manager\n',
        "RPC policy reference",
    )
    replace_once(
        rpc,
        '        if method in ORDER_METHODS and not self.allow_order_methods:\n            raise PermissionError("order rpc methods are disabled")\n        # query_stock_positions is list-shaped in MiniQMT.',
        '        if method in ORDER_METHODS and not self.allow_order_methods:\n            raise PermissionError("order rpc methods are disabled")\n        if method in ORDER_METHODS and self.order_admission is not None:\n            allowed, reason = self.order_admission.evaluate(params, method=method)\n            if not allowed:\n                raise PermissionError("BigQMT order admission blocked: %s" % reason)\n        # query_stock_positions is list-shaped in MiniQMT.',
        "RPC policy dispatch",
    )
    replace_once(
        rpc,
        '        result = self.order_gateway.cancel(order_ref, account_id=account_id)\n\n        # The native cancel return is not trustworthy in EITHER direction.',
        '        if getattr(self.order_gateway, "admission", None) is not None:\n            strategy_name = str(\n                params.get("strategy_name") or self.default_strategy_name).strip()\n            if not strategy_name:\n                raise PermissionError("cancel requires an allowlisted strategy_name")\n            try:\n                raw_orders = self.order_gateway.query_orders_strict(account_id, "") or []\n                strategy_orders = self._attribute_to_strategies(account_id, raw_orders)\n            except Exception as exc:\n                raise PermissionError("cancel ownership query failed: %s" % exc)\n            owned = [\n                item for item in strategy_orders\n                if str(getattr(item, "order_sys_id", "") or "") == order_sys_id\n                and str(getattr(item, "strategy_name", "") or "").strip() == strategy_name\n            ]\n            if not owned:\n                raise PermissionError(\n                    "cancel blocked: broker order is not attributable to strategy %s"\n                    % strategy_name)\n            result = self.order_gateway.cancel(\n                order_ref, account_id=account_id, strategy_name=strategy_name)\n        else:\n            result = self.order_gateway.cancel(order_ref, account_id=account_id)\n\n        # The native cancel return is not trustworthy in EITHER direction.',
        "cancel attribution boundary",
    )


def version_from(package: Path) -> str:
    content = (package / "version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', content, re.M)
    if not match:
        raise RuntimeError("upstream version.py has no __version__ stamp")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", type=Path, required=True,
                        help="upstream bigqmt_signal_trader package directory")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="new candidate directory; must not already exist")
    args = parser.parse_args()
    upstream = args.upstream_dir.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        raise SystemExit("refusing to overwrite candidate: %s" % output)
    if not (upstream / "adapter_factory.py").is_file() or not (upstream / "redis_rpc.py").is_file():
        raise SystemExit("not an upstream bigqmt_signal_trader package: %s" % upstream)
    for item in SAFEGUARD_FILES:
        if not (LOCAL_PACKAGE / item).is_file():
            raise SystemExit("missing local safeguard source: %s" % (LOCAL_PACKAGE / item))

    shutil.copytree(str(upstream), str(output))
    for item in SAFEGUARD_FILES:
        target = output / item
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(LOCAL_PACKAGE / item), str(target))
    install_local_execution_boundary(output)
    if not compileall.compile_dir(str(output), quiet=1):
        raise SystemExit("candidate compile check failed")

    manifest = {
        "schema_version": 1,
        "upstream_version": version_from(output),
        "upstream_source": str(upstream),
        "safeguards": [str(item).replace("\\\\", "/") for item in SAFEGUARD_FILES] + [
            "adapter_factory.execution_admission_wrapper",
            "redis_rpc.order_entry_admission",
            "redis_rpc.cancel_strategy_attribution",
        ],
        "sha256": {str(path.relative_to(output)).replace("\\\\", "/"): sha256(path)
                   for path in sorted(output.rglob("*.py"))},
    }
    (output / "UPGRADE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "prepared", "version": manifest["upstream_version"],
                      "candidate": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
