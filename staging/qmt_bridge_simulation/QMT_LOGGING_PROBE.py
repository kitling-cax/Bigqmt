# -*- coding: gbk -*-
"""QMT Python execution probe.

Purpose: prove that a newly created strategy reaches QMT's Python runtime.
Safety: logging only.  It does not import Redis, query an account, subscribe
extra quotes, start a server, or call any trading API.
"""

import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init(ContextInfo):
    """QMT lifecycle callback; expected once at strategy startup."""
    logger.info(
        "[qmt_logging_probe] init ok stock=%s period=%s account=%s",
        getattr(ContextInfo, "stockcode", ""),
        getattr(ContextInfo, "period", ""),
        getattr(ContextInfo, "accountID", ""),
    )
    ContextInfo._kitling_probe_logged_bar = False


def handlebar(ContextInfo):
    """Log once only, so a minute-line run does not flood QMT output."""
    if getattr(ContextInfo, "_kitling_probe_logged_bar", False):
        return
    ContextInfo._kitling_probe_logged_bar = True
    logger.info(
        "[qmt_logging_probe] handlebar ok barpos=%s",
        getattr(ContextInfo, "barpos", ""),
    )
