"""Strictly read-only client for the simulation BigQMT Redis bridge."""

from __future__ import annotations

import json
import base64
import time
import uuid
from dataclasses import dataclass
from typing import Any

from .redis_resp import RedisRespClient


# The Redis client bundled with Big QMT applies a vendor-specific sensitive
# data filter to list responses.  A raw RPC JSON request containing a stock
# code such as ``600519`` can therefore be rejected before the bridge ever
# sees it.  xtquant_big_convert uses this exact wire encoding to hide the
# request text from that filter; keep the constants byte-for-byte compatible.
SAFE_B64_PREFIX = "b64s:"
SAFE_B64_DIGIT_ENCODE = str.maketrans("0123456789", "!#$%&()*~?")


def encode_rpc_request_payload(request: dict[str, Any]) -> str:
    """Encode an RPC request using xtquant_big_convert's safe Redis format."""

    raw = json.dumps(request, ensure_ascii=False).encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii").translate(SAFE_B64_DIGIT_ENCODE)
    return SAFE_B64_PREFIX + encoded


READ_ONLY_METHODS = frozenset((
    "ping",
    "query_stock_asset",
    "query_stock_positions",
    "query_stock_orders",
    "query_stock_trades",
    "get_full_tick",
    "get_market_data_ex",
    "get_trading_dates",
    "get_local_data",
    "get_divid_factors",
    "download_history_data",
))


class ReadOnlyMethodError(PermissionError):
    pass


class RpcResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReadOnlyBigQmtClient:
    redis: RedisRespClient
    account_id: str
    timeout_seconds: float = 12.0

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if method not in READ_ONLY_METHODS:
            raise ReadOnlyMethodError("method is not in the read-only allowlist: %s" % method)
        request_id = uuid.uuid4().hex
        response_key = "bigqmt:rpc:resp:%s:%s" % (self.account_id, request_id)
        request = {
            "schema_version": 1,
            "request_id": request_id,
            "account_id": self.account_id,
            "method": method,
            "params": params or {},
            "reply_channel": response_key,
            "reply_list": "bigqmt:rpc:respq:%s:%s" % (self.account_id, request_id),
            "reply_key": response_key,
            "ttl_seconds": 60,
        }
        queue_key = "bigqmt:rpc:queue:%s" % self.account_id
        # Do not push raw JSON: Big QMT's bundled redis-py scans list replies
        # for stock-code-looking text and raises DataError.  The bridge
        # decodes this exact xtquant_big_convert-compatible envelope.
        self.redis.command("RPUSH", queue_key, encode_rpc_request_payload(request))
        self.redis.command("EXPIRE", queue_key, 60)

        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            raw = self.redis.command("GET", response_key)
            if raw:
                response = json.loads(raw)
                if not response.get("ok", False):
                    raise RpcResponseError("%s: %s" % (method, response.get("error", "unknown RPC error")))
                return response
            time.sleep(0.2)
        raise TimeoutError("read-only RPC timed out: %s" % method)

    def ping(self) -> dict[str, Any]:
        return self.call("ping")

    def account_asset(self) -> dict[str, Any]:
        return self.call("query_stock_asset")

    def positions(self) -> dict[str, Any]:
        return self.call("query_stock_positions")

    def orders(self, strategy_name: str = "") -> dict[str, Any]:
        return self.call("query_stock_orders", {"strategy_name": str(strategy_name or "")})

    def trades(self, strategy_name: str = "") -> dict[str, Any]:
        return self.call("query_stock_trades", {"strategy_name": str(strategy_name or "")})

    def full_tick(self, codes: list[str]) -> dict[str, Any]:
        return self.call("get_full_tick", {"codes": list(codes)})

    def market_data_ex(
        self,
        codes: list[str],
        fields: list[str] | None = None,
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        count: int = -1,
        dividend_type: str = "none",
        subscribe: bool = False,
    ) -> dict[str, Any]:
        """Read historical bars through QMT; never a trade method.

        The host-side verification path is cache-only by default.  Big QMT's
        native ``ContextInfo.get_market_data_ex`` defaults ``subscribe`` to
        true, which can turn a cache read into a live quote-service request;
        pass the flag explicitly so a downloaded local bar is tested as such.
        """
        return self.call("get_market_data_ex", {
            "stock_list": list(codes),
            "field_list": list(fields or ["close"]),
            "period": str(period),
            "start_time": str(start_time or ""),
            "end_time": str(end_time or ""),
            "count": int(count),
            "dividend_type": str(dividend_type or "none"),
            "subscribe": bool(subscribe),
        })

    def trading_dates(
        self, market: str = "SH", start_time: str = "", end_time: str = "", count: int = -1,
    ) -> dict[str, Any]:
        """Read QMT's exchange calendar; it cannot create an order."""
        return self.call("get_trading_dates", {
            "market": str(market), "start_time": str(start_time or ""),
            "end_time": str(end_time or ""), "count": int(count),
        })

    def download_history_data(
        self, code: str, period: str = "1d", start_time: str = "", end_time: str = "",
    ) -> dict[str, Any]:
        """Request QMT to populate its local historical cache; no account mutation."""
        return self.call("download_history_data", {
            "stock_code": str(code), "period": str(period),
            "start_time": str(start_time or ""), "end_time": str(end_time or ""),
        })

    def local_data(
        self,
        codes: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        count: int = -1,
        dividend_type: str = "none",
    ) -> dict[str, Any]:
        """Read QMT's legacy local-cache API without any subscription."""
        return self.call("get_local_data", {
            "stock_code": list(codes),
            "period": str(period),
            "start_time": str(start_time or ""),
            "end_time": str(end_time or ""),
            "count": int(count),
            "dividend_type": str(dividend_type or "none"),
        })

    def divid_factors(
        self, code: str, start_time: str = "", end_time: str = ""
    ) -> dict[str, Any]:
        """Read QMT's cached dividend/ex-right factor records.

        The bridge adapter accepts a range and, on terminals exposing only a
        single-date ContextInfo method, expands the range using raw daily
        bars.  This remains a read-only RPC and never downloads or mutates the
        shared lake.
        """
        return self.call("get_divid_factors", {
            "stock_code": str(code),
            "start_time": str(start_time or ""),
            "end_time": str(end_time or ""),
        })
