# `.105` 项目下一阶段执行单（2026-09-19）

## 当前已完成

- `.105`、`.125`、`.113` Host Agent Fact 链路已接通，`.121:18666` 信任三台主机。
- `.125` simulation / production_readonly pending=0，两个 Bridge PASS。
- `.113` intent-preview PASS，Fact pending=0，simulation Bridge PASS。
- `.113` production Bridge 仍 DEGRADED，交易时段不重启。
- 所有主机 `orders_enabled=false`，正式账户只读。

## 今天继续推进的安全工作

1. 保持 `.125` 和 `.113` 托盘、Redis、Fact delivery 运行。
2. 今天确认 A 股不交易，按 `docs/179_host113_after_hours_bridge_readonly_recovery_2026-09-19.md` 立即做一次 `.113` 正式 Bridge 只读恢复检查。
3. 将 `.105/.125/.113` 的每日 Bridge、Fact、策略运行证据归档到 NAS。
4. 开始 P05 策略包清单：每个策略固定 `strategy_id`、版本、哈希、允许账户、允许主机和回滚版本。
5. 设计本地授权 Key 接入，但先只做校验和观察，不改变当前订单锁。

## 本地授权 Key 的最终边界

- Key 保存在本机受保护目录，模拟和正式分开；
- Key 校验成功只表示本机具备账户执行资格；
- 本机 QMT、Redis、Bridge、策略开关和风控检查仍必须通过；
- Coordinator 只做多主机冲突检测、心跳、事实和收益归档；
- 同一账户发现多个有效主机时，全部降级只读；
- Coordinator 不可达时保持只读，避免网络分区造成重复下单；
- 本阶段不修改 `orders_enabled=false`，不开放正式账户。

## `.105` 需要维护的本地证据

```text
runtime_data/audit/<profile>/native_tray.jsonl
runtime_data/evidence/<profile>/bridge_daily/
runtime_data/state/<profile>/host_agent_outbox.sqlite3
```

不得把 QMT 密码、Fact Secret、账户授权 Key 或运行数据库提交 Git/NAS 公共策略库。
