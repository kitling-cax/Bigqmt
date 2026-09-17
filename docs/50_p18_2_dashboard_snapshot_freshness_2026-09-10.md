# P18.2 Dashboard 快照时间与可用性

模拟盘和正式只读 Dashboard 的总览新增“数据快照”指标，显示：

- SQLite WAL 最近快照的完成时间；
- 快照采集状态；
- 截短显示的运行编号，便于与本地审计和数据湖证据定位。

该字段来自本地 `snapshot_runs`，不调用 QMT 或 Redis。正式投影仍只读取正式状态库。

2026-09-10 验证：模拟与正式最新快照均为 `PASSED`，两个 Dashboard 健康检查为 `HEALTHY`，两端订单开关均为关闭。
