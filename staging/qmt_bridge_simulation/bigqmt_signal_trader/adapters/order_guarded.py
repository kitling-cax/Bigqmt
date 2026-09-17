"""In-process order/cancel guard shared with the RPC admission policy."""


class GuardedOrderGateway(object):
    """Wrap a broker gateway; deny writes unless the policy admits them.

    Query methods are intentionally delegated unchanged.  The class protects
    SignalTradingApp, while Redis RPC has a second check at its entry point.
    """

    def __init__(self, gateway, admission):
        self._gateway = gateway
        self.admission = admission
        # Read-only metadata exposed explicitly.  Do not use __getattr__: an
        # unrestricted delegate also exposes the raw passorder callable and
        # silently turns this safety wrapper into an escape hatch.
        self.account_type = gateway.account_type
        self.combo_type = gateway.combo_type
        self.price_type = gateway.price_type
        self.quick_trade = gateway.quick_trade
        self.get_trade_detail_data = gateway.get_trade_detail_data

    @staticmethod
    def _request_params(request):
        return {
            "account_id": getattr(request, "account_id", ""),
            "strategy_name": getattr(request, "strategy_name", ""),
        }

    def submit(self, request):
        allowed, reason = self.admission.evaluate(
            self._request_params(request), method="submit_order")
        if not allowed:
            raise PermissionError("BigQMT order blocked: %s" % reason)
        return self._gateway.submit(request)

    def cancel(self, order_ref, account_id=None, strategy_name=None):
        allowed, reason = self.admission.evaluate(
            {"account_id": account_id or "", "strategy_name": strategy_name or ""},
            method="cancel_order")
        if not allowed:
            raise PermissionError("BigQMT cancel blocked: %s" % reason)
        return self._gateway.cancel(order_ref, account_id=account_id)

    def passorder_passthrough(self, op_type, order_type, account_id,
                              order_code, price_type, price, volume,
                              strategy_name, quick_trade, user_order_id,
                              dry_run=False):
        allowed, reason = self.admission.evaluate(
            {"account_id": account_id or "", "strategy_name": strategy_name or ""},
            method="passorder")
        if not allowed:
            raise PermissionError("BigQMT native passorder blocked: %s" % reason)
        return self._gateway.passorder_passthrough(
            op_type=op_type,
            order_type=order_type,
            account_id=account_id,
            order_code=order_code,
            price_type=price_type,
            price=price,
            volume=volume,
            strategy_name=strategy_name,
            quick_trade=quick_trade,
            user_order_id=user_order_id,
            dry_run=dry_run,
        )

    # Explicitly delegated read-only operations required by Redis RPC.
    def _resolve_account_type(self, account_id):
        return self._gateway._resolve_account_type(account_id)

    def _account_type_code(self, account_id=None):
        return self._gateway._account_type_code(account_id)

    def query_orders(self, account_id, strategy_name):
        return self._gateway.query_orders(account_id, strategy_name)

    def query_orders_strict(self, account_id, strategy_name):
        return self._gateway.query_orders_strict(account_id, strategy_name)

    def query_trades(self, account_id, strategy_name):
        return self._gateway.query_trades(account_id, strategy_name)

    def query_trades_strict(self, account_id, strategy_name):
        return self._gateway.query_trades_strict(account_id, strategy_name)

    def query_submission_identities_strict(self, account_id, strategy_name):
        return self._gateway.query_submission_identities_strict(
            account_id, strategy_name)

    def describe_detail_fields(self, account_id, detail_types=None,
                               shape_fields=None):
        return self._gateway.describe_detail_fields(
            account_id, detail_types=detail_types, shape_fields=shape_fields)
