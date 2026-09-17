# `.121:18666` Shadow 事实接收验证（`.105` 合成事实）

日期：2026-09-17 12:08（Asia/Shanghai）

## 目的与边界

本次只验证 Host Agent 事实传输链，不验证下单、不申请 Lease、不改变 `.121:18443` 权威 Coordinator，也不把账户执行授权 Key 当作事实签名 Secret 使用。

- 目标入口：`http://192.0.2.121:18666/api/v1/facts/ingest`
- 权威入口：`http://192.0.2.121:18443`（本次未改动）
- Host：`192.0.2.105`
- Fact key-id：`host-105-fact-shadow-20260917`
- 账户字段：`90000001`（仅作为合成事件字段）
- 策略字段：`v1.1.15|5d|U25-no-alcohol`（仅作为合成事件字段）
- Secret 文件：仅保存于本机受保护目录及 `.121` 容器 Secret 挂载，不进入项目树、NAS 或报告。

## 部署检查

1. Shadow 容器 `kitling-bigqmt-coordinator-shadow` 为 `running|healthy`，容器用户为非 root `uid=10001`。
2. `/secrets/fact-identities.json` 权限为 `0440 root:10001`，容器内可读。
3. Shadow `/readyz` 返回 `200`；权威 `/readyz` 返回 `200`。
4. Shadow 事实入口已启用；权威 `/api/v1/facts/ingest` 仍返回 `404`，因此没有把新写入口带入生产权威服务。

## 签名接收与重放结果

使用本地 `load_credentials()` 读取受保护 Secret，构造合法 UUID `request_id`、HMAC-SHA256 envelope 和一个合成 `STRATEGY_RUNTIME` 事件；没有输出 Secret 内容。

| 场景 | HTTP | 结果 |
|---|---:|---|
| 首次 POST 同一签名 envelope | 202 | `status=ACCEPTED`，接受 `105-shadow-synthetic-20260917-002` |
| 原样再次 POST 同一 envelope | 202 | `status=REPLAYED`，`accepted=[]`、`duplicates=[]` |
| 空 JSON（负例） | 400 | `FactAuthenticationError` |

两次成功响应均包含：`readonly=true`、`facts_only=true`、`orders_enabled=false`。本次请求不调用 QMT、Redis、订单、Lease 或确认接口。

## 结论与下一步

- C2 认证事实链已在 Shadow 完成一次合成接收与重放拦截验证。
- 这不是 `.105` 真实 Outbox 的在线接入证据；真实 Host Agent 上传仍保持未接入，需下一步先在 `.105` 建立只读 Outbox 生成/投递任务，再在 Shadow 观察 ACK 与断网重试。
- `.121:18443` 继续作为唯一权威 Coordinator；在 Host Agent 证据和 24–48 小时 Shadow soak 完成前，不启用权威事实入口。
- 全局订单边界保持关闭：`orders_enabled=false`。
