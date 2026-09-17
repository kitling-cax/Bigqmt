# 145 · Host Agent Outbox 签名投递编排

日期：2026-09-16  
状态：本地实现与测试通过；未在 `.121` 启用网络事实接收。

## 投递流程

```text
SQLite Outbox PENDING → 按 event_id 排序取批次 → Host Fact Secret 签名 envelope
→ HTTPS 传输层（下一步接入）→ Coordinator ACCEPTED / REPLAYED
→ 仅 ACK 明确属于本批次的 event_id
```

新增 `src/kitling_bigqmt/host_fact_uploader.py`：

- `build_pending_envelope()` 无网络副作用，仅生成待发送批次和 ID 清单；
- `acknowledge_fact_batch()` 只接受 Coordinator 明确返回的 `accepted`/`duplicates`；
- `REJECTED`、空 ACK、未知 event ID、超时都不会清除 pending；
- `REPLAYED` 只有在调用方提供原始批次 ID 时才会 ACK；
- 没有 QMT、Redis、Lease、订单或撤单调用。

批次签名、明确 ACK、错误 ACK 保留 pending、拒绝响应和认证事实测试均通过；全量 `261 passed`。

下一步：将编排接到 Windows Host Agent 后台任务；在 `.121:18666` 配置 Secret 后做 HTTPS 事实上传回放；通过 Shadow 门禁后再纳入 Dashboard。
