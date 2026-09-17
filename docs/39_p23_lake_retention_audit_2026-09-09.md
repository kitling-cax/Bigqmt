# P23 数据湖留存审计（2026-09-09）

## 已完成

新增 `scripts/audit_lake_retention.py`，只读扫描 `runtime_data/lake/<environment>/<trading_date>/<source_run_id>/`：

- 检查每个导出运行是否存在 `manifest.json`；
- 统计文件大小和运行数量；
- 按保留天数标记清理候选；
- 输出 `orders_enabled`、`read_only` 等安全字段；
- 不连接 QMT/Redis，不删除或移动任何文件。

同时新增 `scripts/run_lake_cycle.py`，托盘菜单可调用一次完整的“快照导出 + 留存审计”周期。没有已落盘快照时返回 `BLOCKED`，不会尝试主动连接 QMT，也不会创建委托。

每次周期（包括 `BLOCKED`）都会写入 `runtime_data/evidence/<profile>/lake_cycles/lake_cycle_<UTC>.json`，托盘审计日志会记录状态、导出返回码和证据文件路径。

模拟托盘已增加本地定时触发：默认每天 16:10（收盘后）最多尝试一次；当天成功或阻塞后均不重复执行。正式只读托盘暂不自动写入数据湖，待 P13 独立正式投影完成后再启用。时间可通过启动参数调整，未使用 Windows 任务计划。

默认保留期为 365 天，已写入 `config/data_lake.yaml`。清理动作保持关闭，未来必须另行批准并设计可恢复流程。

## 验证

- `py scripts/audit_lake_retention.py --retention-days 365` 可执行并输出 JSON 报告。
- `py scripts/run_lake_cycle.py --profile simulation --retention-days 365` 已成功完成一次导出与审计；当前共 3 个模拟导出运行，0 个缺失 manifest，0 个清理候选。
- 新增 2 项单元测试，覆盖旧运行候选和缺失 manifest。
- 当前数据湖同步仍是 SQLite WAL → Parquet；DuckDB 只读查询 Parquet；QuestDB 保持 deferred。

P20 运维告警层已接入 Dashboard：`scripts/check_ops_alerts.py` 可离线读取当前状态并输出告警，覆盖订单开关异常、Bridge 异常、行情陈旧/未知、湖周期阻塞和活动门禁。告警只读，不触发交易动作。
