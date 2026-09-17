# P13 正式盘独立只读 Dashboard 投影

## 交付

- 模拟盘 Dashboard：`http://127.0.0.1:17890/simulation/overview`
- 正式盘 Dashboard：`http://127.0.0.1:17891/production-readonly/overview`
- 两个托盘会在启动时自动拉起各自的本机 Dashboard；仍可从托盘菜单打开页面。

## 隔离与安全边界

- 正式投影只读取 `host_gateway.production_readonly.json` 指向的正式 SQLite WAL 状态库；不回退读取模拟状态库。
- 正式投影不展示模拟策略袖套、v1.1.15 影子信号、模拟阻塞项或模拟策略池。
- 两个 `/api/status` 都固定返回 `read_only=true`、`orders_enabled=false`、`order_actions_exposed=false`。
- 正式托盘和页面不提供下单、撤单、策略执行或账户配置入口。

## 本次验证

- 全部测试：`54 passed`。
- 模拟盘与正式盘的托盘健康检查均为 `HEALTHY`：项目配置、Redis、订单锁与各自 Dashboard 均通过。
- 正式 API 实测：profile=`production_readonly`、environment=`production`、持仓快照 1 条、策略袖套 0、影子信号 0、订单能力关闭。

正式账户保持只读；该页面是本机观测投影，不触发 QMT、Redis 写入或任何交易操作。
