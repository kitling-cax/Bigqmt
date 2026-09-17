#coding:gbk
#
# Simulation-only QMT editor entry.
# The QMT formula loader in this terminal requires callbacks to be defined in
# the editor script itself.  Each callback below forwards to the staged Bridge.
# Keep this file ASCII-only when pasting it into the QMT editor.

import bigqmt_signal_trader_strategy as _bridge

try:
    ACCOUNT_ID = account
except NameError:
    ACCOUNT_ID = ""

if ACCOUNT_ID:
    _bridge.set_account_id(ACCOUNT_ID)

_bridge.configure(mode="dryrun", account_id=ACCOUNT_ID or "dryrun")


def init(ContextInfo):
    return _bridge.init(ContextInfo)


def handlebar(ContextInfo):
    return _bridge.handlebar(ContextInfo)


def adjust(ContextInfo):
    return _bridge.adjust(ContextInfo)


def order_callback(ContextInfo, orderInfo):
    return _bridge.order_callback(ContextInfo, orderInfo)


def deal_callback(ContextInfo, dealInfo):
    return _bridge.deal_callback(ContextInfo, dealInfo)


def sync_positions(ContextInfo):
    return _bridge.sync_positions(ContextInfo)
