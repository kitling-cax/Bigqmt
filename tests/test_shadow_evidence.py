from kitling_bigqmt.shadow_evidence import assess_shadow_events


def test_shadow_evidence_is_informational_not_an_execution_gate():
    event = {
        "signal_day": "20260911",
        "orders_enabled": False,
        "broker_call_made": False,
        "execution_intent": "NONE_CLOSE_SIGNAL_ONLY",
        "bar_coverage": {"160723.SZ": 25},
        "state_before": {"current": None},
        "state_after": {"current": "160723.SZ"},
    }
    assessment = assess_shadow_events([event])
    assert assessment["evidence_complete"] is True
    assert assessment["simulation_order_admission"] == "NOT_DECIDED_BY_SHADOW_EVIDENCE"
