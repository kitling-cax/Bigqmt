# P20 运行恢复与 fail-closed 记录（2026-09-10）

## 现象

系统重启/进程退出后，两个托盘和本地 Dashboard 未在运行；模拟 Redis/QMT 暂时不可达。

## 处理

- 只恢复本地 Dashboard 和两个托盘进程；没有启动或登录 QMT，没有重启 Redis。
- Dashboard `healthz=ok`，`/api/status` 返回 `read_only=true`、`orders_enabled=false`。
- 模拟托盘健康检查：Redis 检查失败，整体状态 `FAIL_CLOSED`；订单锁检查通过。
- 正式托盘继续独立运行，正式账户没有任何交易调用。

## 结论

在 QMT/Redis 恢复前，系统不会采集新的券商快照、不会执行数据湖自动周期，也不会产生任何委托。托盘负责显示异常并等待人工恢复 QMT 连接。
