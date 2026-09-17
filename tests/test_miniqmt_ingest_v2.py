import pandas as pd
import pytest
from kitling_bigqmt.lake_ingest_v2 import BronzeIngestError, normalize_miniqmt

def test_miniqmt_import_requires_explicit_units():
    frame=pd.DataFrame([{ "code":"510300.SH", "trade_date":"20260911", "open":4.6, "high":4.7, "low":4.5, "close":4.65, "volume":100, "amount":465000 }])
    with pytest.raises(BronzeIngestError, match="units must be measured"):
        normalize_miniqmt(frame,"m","UNVERIFIED","UNVERIFIED")
    out=normalize_miniqmt(frame,"m","lots","cny",{"510300.SH"})
    assert out.iloc[0]["source"]=="miniqmt" and out.iloc[0]["asset_class"]=="etf"
