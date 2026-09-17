# M03 Windows Host Agent：空只读 Intent Preview

日期：2026-09-14  
状态：本地实现与回归通过；未部署至 Coordinator `.121`。

## 本批交付

- `host_agent_intent_preview.py`：仅接受明确的 `readonly=true`、`orders_enabled=false`、
  当前 profile/host 匹配且 `intents=[]` 的 envelope；任一实际 intent、错误模式、账户或主机不匹配
  均失败关闭。
- `HostAgentClient.readonly_intent_preview()`：只发送 HTTP `GET` 到
  `/api/v1/host-agent/intents`，无 request body；没有提交、确认、轮询确认、租约、QMT、Redis 或
  Shell 方法。
- Coordinator 本地 bootstrap 增加同名端点，只返回空 preview。端点不读取 SQLite `intents` 表、
  不读取 lease、也不暴露任何订单内容。

## 安全边界

该端点是 Windows Host Agent 与 Coordinator 的网络/合同连通缝，不是模拟订单功能。任何要返回
真实 intent、发放 lease、写确认或调用 Bridge 的变更都必须进入 M06，完成独立合同、鉴权、
用户 AP5 和模拟环境验收后才可实现。

## 验收

```text
py -3.12 -m pytest -p no:qt -q tests
158 passed in 12.42s
```

包含 Host Agent GET-only、空 envelope、意图行拒绝、账户/主机/模式拒绝、Coordinator HTTP
端到端与现有 lease/heartbeat 回归。测试未连接 QMT、Redis 或真实 `.121` 服务，也没有下单。
