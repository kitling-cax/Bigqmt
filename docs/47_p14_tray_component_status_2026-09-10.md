# P14 托盘组件状态与本机 Dashboard 自恢复

托盘菜单现在固定显示四项只读组件状态：

- Bridge snapshot：对应 profile 的本地 SQLite WAL 最新 Bridge 快照；不调用 QMT RPC。
- Redis：对该 profile 的 Redis 端口执行只读 `PING`。
- Dashboard：只检查对应 loopback Dashboard 的只读健康端点。
- Order lock：检查运行控制文件的订单与执行消费者均为关闭。

“Ensure local read-only Dashboard is running”只会在本机 Dashboard 不在线时启动该 profile 的本地只读页面；不会停止/重启 QMT、Redis 或 Bridge，也不改变订单锁。

2026-09-10 验证结果：模拟盘与正式盘四项均为 `PASS`，两个托盘进程均已重新启动加载本菜单，订单能力保持关闭。
