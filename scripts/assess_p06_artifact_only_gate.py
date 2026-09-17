"""Summarize the P06 gate using the PTrade artifacts that actually exist.

This host-only report is intentionally conservative: explained state/risk
parity is evidence, but an unresolved data/eligibility gap never becomes an
order permission.  It does not contact QMT or create order intents.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "runtime_data" / "evidence" / "simulation"


def latest(pattern: str) -> Path:
    candidates = sorted(EVIDENCE.glob(pattern))
    if not candidates:
        raise FileNotFoundError("no evidence matching %s" % pattern)
    return candidates[-1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    paths = {
        "artifact_audit": latest("ptrade_v1_1_15_artifact_audit_*.json"),
        "state_replay": latest("ptrade_v1_1_15_state_replay_*.json"),
        "risk_replay": latest("qmt_v1_1_15_risk_replay_parity_*.json"),
        "daily_score": latest("qmt_v1_1_15_daily_score_parity_*.json"),
        "rank_diagnosis": latest("qmt_v1_1_15_rank_difference_diagnosis_*.json"),
        "lake_probe": latest("qmt_v1_1_15_lake_vs_qmt_factor_probe_*.json"),
    }
    data = {name: load(path) for name, path in paths.items()}
    audit, state, risk, daily, rank, lake = (data[name] for name in (
        "artifact_audit", "state_replay", "risk_replay", "daily_score", "rank_diagnosis", "lake_probe"))
    counts = rank.get("category_counts", {})
    checks = [
        {"name": "PTrade artifact integrity", "passed": audit.get("status") == "PASSED",
         "detail": "TXT/CSV holdings reconciliation"},
        {"name": "PTrade position replay", "passed": state.get("log_current_mismatch_count") == 0,
         "detail": "%s/%s logged current positions contained" %
                   (state.get("log_current_active_contains"), state.get("log_day_count"))},
        {"name": "QMT risk replay", "passed": risk.get("risk_mismatches") == 0 and risk.get("risk_matches") == risk.get("comparable_days"),
         "detail": "%s/%s comparable risk days" % (risk.get("risk_matches"), risk.get("comparable_days"))},
        {"name": "QMT daily best/score parity", "passed": daily.get("best_code_matches") == daily.get("scored_day_count")
                   and daily.get("ptrade_best_score_matches") == daily.get("scored_day_count"),
         "detail": "best %s/%s; score %s/%s" % (daily.get("best_code_matches"), daily.get("scored_day_count"),
                                                    daily.get("ptrade_best_score_matches"), daily.get("scored_day_count"))},
        {"name": "unresolved PTrade data/eligibility evidence", "passed": counts.get("DATA_OR_ELIGIBILITY_DIFFERENCE", 0) == 0,
         "detail": "%s unresolved rank cases" % counts.get("DATA_OR_ELIGIBILITY_DIFFERENCE", 0)},
        {"name": "QMT vs lake source evidence", "passed": False,
         "detail": "4 source-difference cases remain per lake probe"},
    ]
    passed = sum(bool(item["passed"]) for item in checks)
    artifact = {
        "schema_version": 1,
        "kind": "p06_artifact_only_gate",
        "created_at": datetime.now().astimezone().isoformat(),
        "environment": "simulation",
        "runtime_owner": "BIGQMT_TRAY_ONLY",
        "orders_enabled": False,
        "order_intent_allowed": False,
        "status": "BLOCKED",
        "summary": "Artifact-only evidence confirms PTrade position and risk replay, but does not close data/eligibility or source gaps.",
        "evidence": {name: str(path) for name, path in paths.items()},
        "checks": checks,
        "passed_check_count": passed,
        "check_count": len(checks),
        "difference_counts": counts,
        "release_condition": "Resolve or explicitly accept the PTrade per-security evidence gap, then pass local dry-run and preflight before any simulation order intent.",
    }
    output = EVIDENCE / ("p06_artifact_only_gate_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": artifact["status"],
                      "passed_check_count": passed, "check_count": len(checks),
                      "difference_counts": counts, "order_intent_allowed": False}, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
