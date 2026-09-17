# P16：托盘双终端自动启动与免密边界

日期：2026-09-13  
范围：本机两个账户 profile；不包含任何订单或撤单动作。

## 已交付

每个原生托盘 EXE 的“服务管理”提供两个独立入口：

1. **启动缺失的 QMT**：启动 `XtItClient.exe`。配置为 `mode=login` 时，账号和密码仅从 Windows Credential Manager 读取，并通过已解锁的本机交互桌面填写登录框。
2. **启动缺失的 MiniQMT（免密）**：启动 `XtMiniQmt.exe linkMini`。该路径不读取、保存、输出或传递 MiniQMT 密码。

托盘每 30 秒显示 QMT、MiniQMT、Redis、Bridge、Dashboard 的独立状态；对于停止的 QMT 或 MiniQMT，最多每两分钟提交一次启动请求。它不会自动结束、强制重启或循环重启仍在运行的任意终端。

## 监控语义

- `XtItClient.exe` 运行，只表示“大 QMT 主进程存在”；不代表登录、账户匹配或 Bridge 可下单。
- `XtMiniQmt.exe` 运行，只表示“MiniQMT 进程存在”；不代表账户、行情或交易接口已就绪。
- 只有本 profile 的新鲜 Bridge RPC/快照可证明大 QMT 的账户链路；正式账户仍硬性只读。
- QMT/ MiniQMT 任一缺失时托盘显示为降级并尝试补拉，但订单锁保持关闭。

## 验证记录

- 两个目标安装目录均确认存在 `XtItClient.exe`、`XtMiniQmt.exe` 与 `miniquote.exe`。
- `scripts/miniqmt_launcher_cli.py status` 已在 simulation 与 production_readonly profile 验证为可执行，当前均返回 `STOPPED`，未启动终端。
- 原生托盘 EXE 已重新编译；相关 Python 测试 4 项通过。
- 发布清单：`runtime_data/evidence/tray/manifest_miniqmt_autostart_20260913.json`。

## 尚待人工终端证据

启动两只新 EXE 后，分别观察 MiniQMT 项是否从“未运行（将自动补拉）”变为“运行中（免密，PROCESS ONLY）”。若券商终端弹出额外确认、验证码或登录异常，托盘只会记录失败并保持订单锁，不会猜测或绕过。

## 2026-09-13 登录修复验证

FormulaServer `58600` 是主机共享端口，不能作为某一 profile 已登录的证明；默认 `QMT` 标题匹配也会混淆两套登录框。启动器已改为 profile 固定窗口前缀，模拟为 `国金QMT交易端模拟`，正式为 `国金证券QMT交易端`，并新增 `LOGIN_DIALOG / MAIN_WINDOW` 状态。

- 正式已有登录框从 `LOGIN_DIALOG` 自动完成为 `MAIN_WINDOW`；之后只读 Bridge ping 成功（281ms）。
- 模拟终端被启动后，也从 `LOGIN_DIALOG` 自动完成为 `MAIN_WINDOW`。
- 两个新版托盘 EXE 已重新编译并启动。模拟 Bridge 当时超时，被明确显示为 Bridge 降级，不会误判成登录失败。
