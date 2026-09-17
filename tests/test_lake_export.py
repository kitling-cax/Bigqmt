from pathlib import Path

import duckdb

from scripts.export_readonly_snapshot_to_lake import _write


def test_empty_lake_dataset_keeps_parquet_schema(tmp_path: Path):
    target = tmp_path / "broker_orders.parquet"
    _write([], target, ["row_key", "source_run_id", "environment"])
    assert duckdb.sql("select count(*) from read_parquet(?)", params=[str(target)]).fetchone()[0] == 0
    columns = [row[0] for row in duckdb.sql("describe select * from read_parquet(?)", params=[str(target)]).fetchall()]
    assert columns == ["row_key", "source_run_id", "environment"]
