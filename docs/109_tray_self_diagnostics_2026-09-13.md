# BigQMT Tray 自动日志诊断

## 目的

当 Windows 通知区域没有显示 BigQMT Tray 图标时，不依赖图标本身生成一份只读诊断报告。诊断不会启动、关闭或登录 QMT，不会发出 Redis Bridge 下单或撤单请求，也不会改动策略开关。

## 入口

```powershell
py -3.12 scripts\diagnose_tray.py --profile simulation
py -3.12 scripts\diagnose_tray.py --profile production_readonly
```

## 原生 EXE 发布

每个账户都有一个独立的原生托盘 EXE，分别位于：

- `tray\BigQMT_Simulation_90000001.exe`（模拟盘 90000001）
- `tray\BigQMT_Production_ReadOnly_90000002.exe`（正式只读 90000002）

这是由 Windows 自带 .NET 编译器直接编译的 EXE，不使用 PyInstaller 自解压、加壳或混淆。两个 EXE 都不含下单或撤单菜单。
EXE 图标和托盘图标使用账户专属标识：模拟盘为天蓝色 `S`，正式只读为深蓝色 `P`；运行状态异常或降级时托盘图标变为深红色。
`S/P` 字母采用放大且居中的字形，便于在资源管理器和通知区域的小图标尺寸下区分账户。
对应 SHA-256 在 `tray\BigQMT_native_tray_checksums.sha256`；若更换源码或重新构建，哈希会更新。当前 EXE 未使用代码签名证书，迁移到其他电脑或长期部署前建议使用企业/个人代码签名证书签名。

报告分别写入：

- `runtime_data\audit\simulation\tray_diagnostic_latest.json`
- `runtime_data\audit\production_readonly\tray_diagnostic_latest.json`

## 报告内容

- 当前托盘 PowerShell 进程及精确启动命令。
- 启动器交接记录 `tray_launcher.jsonl`。
- 托盘生命周期记录 `tray_events.jsonl`。
- 界面初始化前异常 `tray_bootstrap_errors.log`。
- 启动子进程的标准错误 `tray_child_stderr.log`。
- Redis、Dashboard、持久化 Bridge 快照和订单锁的只读健康状态。

## 诊断代码

- `TRAY_PROCESS_RUNNING`：脚本仍驻留；若无图标，检查 Windows 的“隐藏图标”区域或 Explorer。
- `TRAY_BOOTSTRAP_ERROR`：WinForms 初始化前失败，查看 `bootstrap_errors.log`。
- `TRAY_EXITED_AFTER_SPAWN`：启动器创建了子进程，但子进程已退出。
- `TRAY_EXITED_AFTER_START`：脚本进入过托盘逻辑，但目前没有驻留进程。
- `NO_LAUNCH_ATTEMPT_RECORDED`：没有通过本项目启动器的记录，需核对启动的 CMD 文件路径。

## 当前结论（2026-09-13）

两个 profile 的历史记录都显示 `tray_started`，但诊断时均没有驻留托盘 PowerShell 进程；不存在 bootstrap 错误。Redis 和两个本地 Dashboard 通过健康检查，订单锁保持关闭。Bridge 持久化快照过期，因此运行状态为 `DEGRADED`，不能被当成 QMT 已准备好的证明。
