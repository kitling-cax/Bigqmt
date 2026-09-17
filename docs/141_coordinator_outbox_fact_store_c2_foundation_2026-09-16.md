# 141 · Coordinator Outbox 与事实去重 C2 基础

日期：2026-09-16  
状态：本地实现与测试通过；未开放网络写入接口；未上报真实订单或成交。

## 完成内容

`src/kitling_bigqmt/coordinator_outbox.py` 新增 Windows Host Agent 可复用的本地 SQLite WAL Outbox：

- 允许的事实类别仅为 `ORDER_EVENT`、`TRADE_FILL`、`STRATEGY_RUNTIME`、`STRATEGY_NAV`、`CHECKPOINT`；
- 每项必须有稳定 `event_id`、`account_id` 和 canonical SHA-256；
- 相同 `event_id` + 相同内容为安全重复，内容不同为 collision 并拒绝；
- 断网失败仅增加 attempts/last error，不删除未确认事件；
- Coordinator 确认后才标为 `ACKED`；
- 拒绝 `password`、`secret`、`credential`、`authorization_key`、`access_token` 等敏感字段；不保存本机授权 Key 明文。

`src/kitling_bigqmt/coordinator_event_store.py` 新增 Coordinator 侧的 SQLite 事实去重库：同一事件只入库一次，篡改重放整批失败。它不是订单队列、不返回执行指令、不会调用 QMT/Redis/券商。

## 当前安全边界

网络 ingest 端点**尚不存在**。当前 bootstrap Coordinator 对：

```text
POST /api/v1/facts/ingest
POST /api/v1/orders
POST /api/v1/leases
```

均返回 `404`。在定义 Host Agent 身份签名、TLS/证书或等价传输可信边界、请求重放保护和账户/主机绑定前，不将事实写接口暴露到 `.121` 内网。

## 验证

```text
Outbox / bootstrap 路由边界定向测试：14 passed
全项目：252 passed in 17.19s
```

## 下一步

1. 定义每台 Host Agent 的可迁移身份与签名 envelope；身份材料和执行授权 Key 分离。
2. 为 fact ingest 加入主机身份、时间窗口、请求 ID 和 payload hash 校验。
3. 只为认证后的 Host Agent 开放批量事实写入；仍不开放 order/lease/confirm 写接口。
4. 将 Host Agent 托盘的订单、成交、策略运行、NAV、checkpoint 以本地 Outbox 方式接入，并先做 fixture/离线回放。
