# 运行时恢复与候选门禁记录（2026-09-12）

## 运行时恢复

本轮发现两套 Redis 与本地 Dashboard 曾停止监听，导致候选验证第一次出现 31 次 RPC 超时。使用项目配置的相对路径启动 Redis 后，模拟盘 `6379`、正式盘只读 `6380` 均恢复；两个 Dashboard 分别恢复在 `17890`、`17891`。随后启动两个独立托盘管家。

## 当前只读健康结果

模拟盘和正式盘只读配置均为 `HEALTHY`：Redis PING、Bridge 快照、Dashboard HTTP 和订单锁检查全部通过。正式账户订单能力仍硬锁定；本轮未调用 QMT 下单/撤单。

## 候选验证结果

恢复后重跑 `scripts/validate_bigqmt_missing_daily_candidates.py --start 20260820 --end 20260911` 成功：527 条 BigQMT 日线、292 条湖中重叠、235 条缺失候选，价格不一致/质量问题/RPC 错误均为 0。证据见 `runtime_data/evidence/simulation/bigqmt_missing_key_scans/validated_missing_daily_20260912_114604.json`。

## 仍未放行的项目

候选仍为 `CANDIDATE_ONLY`。尚未创建 overlay、尚未写入共享湖、尚未更新 `LATEST`；必须先完成 canonical PIT/复权因子链门禁。
