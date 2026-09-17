# Native Tray facts-only Tick 部署验证

日期：2026-09-17 13:55–13:57（Asia/Shanghai）

## 部署

两个旧托盘进程已退出后，重新编译并覆盖正式 EXE，随后分别启动：

- `tray/BigQMT_Simulation_90000001.exe`
- `tray/BigQMT_Production_ReadOnly_90000002.exe`

本次版本把 facts-only 采集/投递加入现有低频维护调度，每 5 分钟最多执行一次；它与 v1.1.15 策略调度分离，不授予订单、Lease 或确认能力。

校验值：

- 模拟：`9A9EF983574157F7A73992B924E1B282491C2D4D6AC3B0CEF165CDE9803551C5`
- 正式：`020BF9C8DD38AE5B6B022A6E8401C9FDA550A68787183777454EEC6987562050`

## 运行证据

两个托盘进程均正常运行，首次维护 tick 记录：

```text
host_fact_delivery: {"status":"ACCEPTED","http_status":202,"acknowledged":1,"pending":0,"orders_enabled":false,"facts_only":true}
```

随后模拟与正式只读 profile 均恢复为：

```text
status_refreshed: 在线; Redis 正常｜看板 正常｜快照约 27 秒前｜订单锁定
```

本次自动补拉 Redis、Dashboard 后，两个 profile 的健康检查和 Bridge 只读 ping 均通过；生产账户 Bridge 回复 `allow_order_methods=false`。

## 结论

- `.105` Host Agent facts-only 自动 tick 已部署并成功向 `.121:18666` Shadow 投递。
- 本地 Outbox 成功 ACK，未留下 pending。
- `.121:18443` 权威 Coordinator 未开放事实写入，未发送任何订单或 Lease 请求。
- v1.1.15 当日 cycle 因真实成交持有期 guard（4/5）被安全阻断，未产生 broker/order call。
