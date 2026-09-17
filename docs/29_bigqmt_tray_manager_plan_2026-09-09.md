# BigQMT 托盘管家纳入项目计划（2026-09-09）

## 定位

BigQMT Tray 是本机的运行管家，不是策略本身，也不替代 `BIGQMT_BRIDGE`。QMT 负责执行策略，Tray 负责启动、监控、打开 Dashboard、保存日志和发现故障。

## 两个独立运行档案

### 模拟档案

- 账户：`90000001`；
- QMT 路径：`C:\BigQMT\work\国金QMT交易端模拟`；
- Redis：`127.0.0.1:6379`，DB 5；
- Dashboard：模拟账户状态；
- 当前允许推进模拟预检和后续单笔验证。

### 正式只读档案

- 账户：`90000002`；
- QMT 路径：`C:\BigQMT\work\国金证券QMT交易端`；
- Redis：`127.0.0.1:6380`，DB 5；
- Dashboard：正式账户只读状态；
- 禁止订单和撤单能力。

两个档案可以在同一台电脑分别启动，但配置、Redis、SQLite、日志和 Dashboard 状态必须隔离。

## 第一版功能范围

- 托盘菜单：打开模拟 Dashboard、打开正式只读 Dashboard、打开日志目录、查看运行状态、退出；
- 启动检查：QMT 目录、Python 策略进程、Redis 端口、Bridge 心跳、SQLite 状态库；
- 监控：进程退出、Redis 断开、Bridge 无响应、行情门禁失败；
- 恢复：只允许安全重启 Redis/Bridge/Dashboard；恢复后先重新只读对账；
- 记录：每次启动、停止、重启、异常和恢复都写入本地日志；
- 移植：路径和端口全部来自 profile 配置，不写死在程序里。

## 明确不做

- Tray 不直接下单、不撤单；
- 不把 Codex 作为交易运行时；
- 第一版不自动登录 QMT；
- 正式账户不因 Tray 启动而获得写权限；
- 不把模拟和正式状态混在同一个 SQLite 或 Redis DB。

## 后续阶段

1. P14：托盘核心、profile 配置和日志；
2. P15：托盘与 QMT/Redis/Bridge/Dashboard 健康检查；
3. P16：自动登录研究（继续单独审批，默认延后）；
4. P17：正式候选验收。
