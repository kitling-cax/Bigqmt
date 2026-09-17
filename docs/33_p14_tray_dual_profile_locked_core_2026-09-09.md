# P14 托盘双 Profile 锁定核心（2026-09-09）

状态：`IN_PROGRESS`。已交付可部署前的安全核心；尚未启动托盘 GUI，也没有启动 QMT、调用 Redis、调用 Bridge 或产生订单。

## 已实现

`tray/BigQMTTray.ps1` 现在接受两种可并行运行的 profile：

```powershell
powershell -ExecutionPolicy Bypass -File tray\BigQMTTray.ps1 -Profile simulation
powershell -ExecutionPolicy Bypass -File tray\BigQMTTray.ps1 -Profile production_readonly
```

- 互斥锁包含 profile，因此模拟和正式只读两个托盘可分别运行；同 profile 只能运行一个实例；
- 运行状态与“锁定订单”命令都传入 profile；控制文件物理隔离；
- 模拟托盘只能打开 `/simulation/overview` 的本机 Dashboard；
- 正式只读托盘暂时禁用 Dashboard 启动与打开，防止把模拟页面误当成正式账户页面；等待 P13 独立状态投影；
- 任一 profile 的状态不明均显示为锁定，托盘没有开锁、下单或撤单功能；
- 自动登录仍为 `DEFERRED`。

`scripts/bigqmt_runtime.py` 同时支持 `--profile simulation` 和 `--profile production_readonly`。模拟控制文件的历史大写环境标识 `SIMULATION` 已做兼容读取，但无论文件内容如何，运行时均强制 `orders_enabled=false`、`execution_consumer_enabled=false`。

## 本地验证

- PowerShell 已成功解析托盘脚本；
- 两个 profile 的 `status` 都返回 `READ_ONLY_LOCKED`；
- 正式 profile 未创建或修改控制文件，缺失状态按失败关闭返回；
- 新增兼容性单测后，项目自动测试为 `37 passed`。

已补齐两个可直接双击的入口：

```text
tray\launch_simulation_tray.cmd
tray\launch_production_readonly_tray.cmd
```

profile 参数、账号、QMT 根目录、Redis 端口和 Dashboard 能力记录在
`config\tray_profiles.json`。迁移到另一台 QMT 电脑时只需复制项目并调整该配置，不需要改托盘代码。

2026-09-09 已实际启动并确认两个 Windows PowerShell 进程同时存活：

- `simulation` profile：PID 38220；
- `production_readonly` profile：PID 17364。

如果系统托盘区域被 Windows 收起，请展开任务栏右侧的隐藏图标箭头；托盘本身没有主窗口，这是 Windows 通知区域程序的正常表现。

托盘图标已改为运行时生成的项目图标：模拟盘为蓝色圆形 `S`，正式只读为紫色圆形 `P`，不再使用难以区分的系统盾牌图标。修改后两个 profile 已重新启动并确认进程持续存活。

托盘已增加脱敏 JSONL 审计：`runtime_data\audit\simulation\tray_events.jsonl` 与
`runtime_data\audit\production_readonly\tray_events.jsonl` 分开记录启动、健康状态变化、异常、人工锁定和退出。另修复了 Windows PowerShell 自动变量 `Args` 冲突导致状态读取失败的问题。

## 后续

P14 尚需加入受控日志和发布 manifest；P15 已开始接入 Redis/Dashboard 的只读健康检查，后续再增加安全恢复。它们都不含 QMT 自动登录或订单开启功能。
