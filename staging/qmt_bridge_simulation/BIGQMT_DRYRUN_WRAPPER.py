#coding:gbk
#
# QMT editor entry for simulation validation.
# Keep this file ASCII-only when copying into QMT's "New Python Strategy" editor.
# It imports the Bridge installed in the simulation QMT python directory.
# No order API is enabled by this wrapper.

from bigqmt_signal_trader_strategy import (
    adjust,
    configure,
    deal_callback,
    handlebar,
    init,
    order_callback,
    set_account_id,
    sync_positions,
)

try:
    ACCOUNT_ID = account
except NameError:
    ACCOUNT_ID = ""

if ACCOUNT_ID:
    set_account_id(ACCOUNT_ID)

configure(mode="dryrun", account_id=ACCOUNT_ID or "dryrun")
