# `.105` Host Agent 本地 Outbox → `.121:18666` Shadow 投递验证

日期：2026-09-17 12:15（Asia/Shanghai）

## 验证范围

在本机 `.105` 读取两个托盘审计文件的最新状态行，使用本地只读采集器写入 SQLite WAL Outbox；随后用已安装的 Host Fact Secret 生成签名 envelope，投递到 `.121:18666` Shadow facts-only 入口，并按 Coordinator 明确返回的 event ID ACK 本地 Outbox。

本次没有连接 QMT、Redis、订单、Lease、确认接口，也没有向权威 `.121:18443` 发送请求。正式账户 profile 仅采集只读运行事实，不能获得执行权限。

## 产物与结果

- 新增 `scripts/host_agent/collect_runtime_fact.py`：只读审计行 → `STRATEGY_RUNTIME` Outbox 事件；事件 ID 对相同最新审计内容稳定，重复采集幂等。
- 新增 `scripts/host_agent/deliver_fact_outbox.py`：只允许明确的 facts-only Shadow 端口（默认拒绝非 `18666`），网络失败/错误 ACK 保持 pending；当前托盘尚未自动调用该命令。
- 新增 `tests/test_collect_runtime_fact.py`：采集器锁单与幂等测试。
- 模拟 Outbox：`runtime_data/state/simulation/host_agent_outbox.sqlite3`
  - 账户 `90000001`
  - 事件 `00fc2e5d-df3a-5602-ac1f-f1b0005a4803`
  - Shadow 返回 `202 ACCEPTED`，明确接受该 event ID。
  - 本地 ACK 后 pending=0。
- 正式只读 Outbox：`runtime_data/state/production/host_agent_outbox.sqlite3`
  - 账户 `90000002`
  - 事件 `a316d90e-02c9-57f5-b56e-caa8909f9fb3`
  - Shadow 返回 `202 ACCEPTED`，明确接受该 event ID。
  - 本地 ACK 后 pending=0。

两条响应均包含 `facts_only=true`、`readonly=true`、`orders_enabled=false`。Secret 和临时签名 envelope 均未进入项目树或 NAS；投递完成后临时 envelope 已清理，Host Fact Secret 保留在受保护目录供后续轮换/自动投递使用。

## 下一步

1. 将采集器与投递器接入 `.105` 托盘的低频 Host Agent tick，仅发送 facts-only Outbox，不自动打开任何订单能力。
2. 增加断网、超时、空 ACK、错误 ACK 的保留 pending 与重试 soak；确认 Coordinator/Shadow 重启不丢事实。
3. 之后再为 `.125` 与 `.113` 各自安装独立 Host Fact Secret 和只读 Host Agent；不共享 `.105` Secret。
4. 事实链稳定后，再做策略 NAV、成交、checkpoint 的 NAS 归档和策略迁移延续。
