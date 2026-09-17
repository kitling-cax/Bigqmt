# P16：Bridge 在线探针与终端恢复证据

## 已实现

`scripts/check_bridge_ping.py` 以 profile 专属 Redis、账号和严格只读 RPC
白名单执行一次 `ping`。它的最大超时为 10 秒，托盘以 60 秒节流调用，结果显示为
`Bridge live ping`。探针不读取账户、持仓、行情、委托或成交；更不会创建订单、撤单、
订单意图或修改运行时订单锁。

这条探针解决了两类误判：

1. `XtItClient.exe` 进程已经出现，但登录窗口仍在等待或券商会话未建立；
2. 58600 FormulaServer 正在监听，但它是本机共享端口，无法证明某个 profile 的
   `BIGQMT_BRIDGE` 已处理 RPC。

托盘把它与 SQLite 的历史 `Bridge snapshot` 分开呈现。只要 live ping 不是 `PASS`，
托盘整体状态至少显示为 `DEGRADED`，并保持订单锁关闭。

## 本轮真实结果

- 模拟 profile：`ping` 在约 3.1 秒超时。此前受控终端重启后的 QMT 日志显示
  账号 `90000001` 到券商网关的连接超时；这与“Bridge 未恢复”的探针结果一致。
- 正式只读 profile：`ping` 在约 3.1 秒超时。正式 Bridge 配置已从错误的
  `6380/db0` 对齐到 `6380/db5`，但运行中的 QMT Bridge 仍需要在终端中重新启动以加载。
- 两个结果均不包含订单/撤单 RPC；`broker_call_made=false`、
  `order_capability=false`。

## 验收状态

本地实现与便携部署检查通过，完整测试套件为 `113 passed`。P16 的真实终端验收仍
`BLOCKED`，因为必须由已登录的 QMT 会话恢复/启动 `BIGQMT_BRIDGE` 后，重新收集
profile 专属的只读 ping、账户、持仓、委托、成交和行情证据。

正式账户在上述流程中始终维持 `production_readonly` 和 `orders_enabled=false`。

## 2026-09-13 托盘桌面启动限制

本项目补充了 `scripts/launch_tray_detached.py`：它用 Windows
`DETACHED_PROCESS` 加 `STA` PowerShell 运行托盘，两个 `tray/launch_*.cmd`
均已接入该入口。当前受控开发执行器会回收它启动的所有 Windows UI 子进程，因此不能
用该执行器证明图标常驻。请从当前用户的 Explorer 直接双击两个 CMD 文件；这是独立
桌面启动路径，不会启动 QMT 下单或策略执行。确认图标稳定后，托盘的 Windows 开机启动
开关即可由托盘菜单管理。
