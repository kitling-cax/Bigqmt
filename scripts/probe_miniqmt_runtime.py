"""Probe the installed MiniQMT/xtdata runtime without fetching or trading."""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main() -> int:
    runtime=Path(r"C:\BigQMT\work\国金QMT交易端模拟\bin.x64\Lib\site-packages")
    result={"schema_version":1,"kind":"miniqmt_runtime_probe","created_at":datetime.now(timezone.utc).isoformat(),"mode":"IMPORT_ONLY_NO_DATA_FETCH_NO_BROKER_CALL","runtime_path":str(runtime),"runtime_exists":runtime.exists()}
    if runtime.exists():
        sys.path.insert(0,str(runtime))
        try:
            from xtquant import xtdata
            result.update({"status":"RUNTIME_IMPORT_PASSED","module":str(getattr(xtdata,"__file__", "")),"market_data_ex_callable":callable(getattr(xtdata,"get_market_data_ex",None)),"download_history_callable":callable(getattr(xtdata,"download_history",None))})
        except ModuleNotFoundError as exc:
            # The desktop host currently runs Python 3.12 while QMT ships
            # cp36--cp39 extension builds.  This is an ABI observation, not
            # permission to copy the binary cache or to guess a data source.
            result.update({"status":"RUNTIME_PRESENT_HOST_ABI_INCOMPATIBLE","error":"%s: %s"%(type(exc).__name__,exc),"host_python":"%s.%s"%(sys.version_info.major,sys.version_info.minor),"qmt_embedded_python_expected":"3.6-3.9"})
        except Exception as exc:
            result.update({"status":"RUNTIME_IMPORT_FAILED","error":"%s: %s"%(type(exc).__name__,exc)})
    else: result["status"]="RUNTIME_PATH_UNAVAILABLE"
    result["safety"]={"data_fetch":False,"lake_write":False,"global_latest_updated":False,"orders_enabled":False,"broker_calls":False}
    out=ROOT/"runtime_data/evidence/simulation/unified_lake_v2/miniqmt_runtime_probe_20260912.json"; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
