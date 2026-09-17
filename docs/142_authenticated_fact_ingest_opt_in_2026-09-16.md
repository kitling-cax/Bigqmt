# 142 · 认证事实接收路由（默认关闭）

日期：2026-09-16  
状态：本地实现与测试通过；未在 `.121` 启用；订单与 Lease 写入仍关闭。

## 实现

新增：

- `src/kitling_bigqmt/coordinator_fact_auth.py`：Host Agent HMAC-SHA256 签名 envelope、主机/key-id 绑定、canonical body hash、签发时间/过期时间和时钟偏差校验；
- `src/kitling_bigqmt/coordinator_fact_ingress.py`：request ID 重放表与事实入库编排；
- `config/schemas/host_fact_envelope.v1.schema.json`：传输合同；
- `scripts/coordinator/serve.py`：可选 `POST /api/v1/facts/ingest` 路由。

## 安全边界

路由只有在以下环境配置同时存在时才启用：

```text
BIGQMT_FACT_INGEST_ENABLED=1
BIGQMT_FACT_TRUSTED_HOSTS_JSON=<受保护的 key_id -> host_id + secret_b64 映射>
```

默认不开启。配置缺失、secret 少于 32 字节、未知 key、主机不匹配、签名错误、body hash 错误、过期或重放请求均拒绝。secret 只能通过服务/容器 Secret 机制提供，不写入代码、普通 JSON、日志或 NAS release。

路由只允许五类事实：`ORDER_EVENT`、`TRADE_FILL`、`STRATEGY_RUNTIME`、`STRATEGY_NAV`、`CHECKPOINT`。它不读取或确认订单意图、不签发 Lease、不调用 QMT/Redis/券商；响应固定携带 `facts_only=true` 和 `orders_enabled=false`。

当前 `.121:18443` 尚未加载此代码，`.121:18666` 也未部署。正式启用前必须先完成 Host Agent 身份材料分发、TLS/内网边界、重放清理策略和 shadow 环境验证。

## 验证

认证 envelope、事实去重、HTTP opt-in 路由及旧只读路由边界测试通过；全项目 `256 passed in 17.28s`。
