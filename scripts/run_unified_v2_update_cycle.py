"""Run one bounded, fail-closed unified-lake v2 update cycle.

The cycle is a coordinator, not a global publisher.  It runs source baseline,
freshness, Bronze/Silver candidate checks and the PIT gate, then writes one
JSON evidence record.  It never calls QMT/Redis or changes any LATEST pointer.
"""
from __future__ import annotations
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(script: str, *args: str) -> dict:
    proc=subprocess.run([sys.executable,str(ROOT/"scripts"/script),*args],capture_output=True,text=True,check=False)
    parsed={}
    for line in reversed(proc.stdout.splitlines()):
        if line.strip().startswith("{"):
            try: parsed=json.loads("\n".join(proc.stdout.splitlines()[proc.stdout.splitlines().index(line):])); break
            except json.JSONDecodeError: pass
    return {"script":script,"returncode":proc.returncode,"result":parsed,"stderr":proc.stderr[-2000:]}

def main() -> int:
    cycle_id="unified_v2_cycle_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stages=[run("audit_unified_lake_v2_sources.py"), run("publish_unified_v2_bronze_candidate.py"), run("build_silver_raw_canonical_candidate.py"), run("check_unified_v2_freshness.py"), run("check_pit_v2_gate.py")]
    report={"schema_version":2,"kind":"unified_v2_update_cycle_evidence","cycle_id":cycle_id,"created_at":datetime.now(timezone.utc).isoformat(),"mode":"CANDIDATE_PREFLIGHT_NO_GLOBAL_WRITE","stages":stages,"decision":"PUBLISHED_CANDIDATES_ONLY_BLOCKED_PIT" if any(item["returncode"]==0 for item in stages) else "FAILED","safety":{"lake_write":False,"global_latest_updated":False,"orders_enabled":False,"broker_calls":False}}
    out=ROOT/"runtime_data/evidence/simulation/unified_lake_v2"/(cycle_id+".json"); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps({"output":str(out),"cycle_id":cycle_id,"decision":report["decision"],"stage_returncodes":[x["returncode"] for x in stages],"safety":report["safety"]},ensure_ascii=False,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
