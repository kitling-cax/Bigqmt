# M01/M02 本地 Coordinator 首批验收

日期：2026-09-14  
范围：本机纯本地控制面；不连接 QMT、Redis、OpenClaw，不发送订单。

## 已交付

- `config/contracts/` 下 heartbeat、account snapshot、executor lease、order intent、order result 五份 v1 JSON 合同。
- `src/kitling_bigqmt/coordinator_core.py`：SQLite WAL、主机心跳、账户租约、fencing token、coordinator epoch、intent preview/confirm、审计。
- `config/coordinator.example.json`：`.121:18443` 初始服务参数、模拟/正式账户边界。
- 租约授予使用 SQLite `BEGIN IMMEDIATE`，在双主抢占竞态下串行递增 fencing token。

## 验收结果

```text
pytest -q tests/test_coordinator_core.py
5 passed

pytest -q tests/test_coordinator_core.py tests/test_machine_config.py tests/test_state_store.py
12 passed

5 contract JSON files valid
progress validation OK
```

验证覆盖：双主租约 fencing、正式账户只读拒绝、epoch 变更使旧租约失效、过期租约拒绝、重复确认拒绝、主机心跳与接管后的最新租约。

## 下一门禁

完成 Fake Host 网络分区/重启故障注入后，生成 Ubuntu 24.04 systemd 只读部署包；部署前仍需确认服务预检和 `.121` 防火墙规则。
