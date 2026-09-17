# BigQMT 托盘管家运行边界

状态：`APPROVED_ARCHITECTURE`。本文件定义日后可移植运行包的生产职责边界；不改变当前
P06 的只读状态，也不启用模拟或正式盘订单。

## 唯一运行入口

`BigQMT Tray` 是部署到 QMT 电脑上的唯一运行入口。QMT 启动、用户完成登录、托盘管家
处于健康状态后，系统应当能够独立完成以下完整链路：

`策略运行 → 信号/目标仓位 → Redis 可靠事件 → QMT 二次校验 → 委托/成交回报 → SQLite 归属与对账 → Dashboard`

托盘管家负责启动和监控本机 Redis、策略主机服务、Dashboard 和本机健康检查；QMT 内置
Python Bridge 负责券商接口与二次校验。它们共同构成 BigQMT 运行系统。

## Codex 边界

Codex 只承担开发、离线验证、审计、报告和人工故障辅助：

- 不启动或维持生产策略；
- 不生成生产订单意图；
- 不调用 QMT 订单或撤单接口；
- 不作为心跳、定时器、重试器或故障恢复依赖；
- 不因未运行而影响已部署 BigQMT 的策略执行。

任何运行期安全决策必须在 BigQMT Tray / Host Gateway / Execution Engine / QMT Bridge 内完成，
不得依赖外部 AI 会话。

## 托盘菜单与 Dashboard

第一版托盘菜单：

- `Open BigQMT Dashboard`：用默认浏览器打开本机 `127.0.0.1` Dashboard；
- `Start Runtime`：仅启动本机 BigQMT 服务，默认订单锁定；
- `Stop Runtime and Lock Orders`：停止本机执行消费并持久化锁单，不强制关闭 QMT；
- `Restart Runtime`：先锁单、停止、重新启动、完成 QMT 事实对账后才恢复只读健康状态；
- 只读状态行：QMT、Redis、Bridge、策略、账户对账、行情新鲜度、订单锁；
- `Reconcile Account Now`、`Open Logs Folder`、`Open Data Folder`、`Exit Tray`。

双击托盘图标应打开 Dashboard。界面参考 OpenCodex 的可见状态、可恢复操作、单实例和本机
心跳模式，但 BigQMT 不复用 OpenCodex 的代理运行逻辑。

## 失败关闭

QMT 二次校验、账户对账、Redis、Bridge、行情新鲜度或环境识别任一异常时：

1. 托盘显示 `WARNING` 或 `LOCKED`；
2. 新订单意图写入拒绝/隔离审计，不自动重投；
3. 重新读取 QMT 的账户、持仓、委托、成交事实；
4. 仅在对账完成且相应环境门禁满足后，才可恢复运行；
5. 正式盘在任何情况下仍保持只读，除非满足正式盘全部门禁并获单独用户批准。

## 可移植要求

发布包不得写死盘符、QMT 路径、账户或登录凭据。首次运行配置本机 QMT `bin.x64` 路径、
数据目录、模拟/正式只读环境和本机端口；运行数据在新电脑重新建立并通过 QMT 对账。QMT
每日登录仍是用户动作，自动登录属于 P14 的后续课题。
