# 2026-09-16 v1.1.15 模拟账户自动交易授权

**决策状态**：已生效
**生效时间**：2026-09-16
**授权范围**：仅模拟账户 90000001；正式账户 90000002 永远只读、永不下单
**决策发起人**：用户
**决策落实人**：Codex（配置 / 记录）

## 用户原话
"因为是模拟账户。无需等我确认。托盘自动决定换仓。"
"现在 v1.1.15 在模拟账户做自动交易。再重申一遍：托盘自己运行策略交易。"

## 落地变更
1. config/strategy_runtime_policy.json：
   - simulation.v1_1_15_preflight_only_dates 从 ["2026-09-16"] 改为 []
   - simulation.v1_1_15_auto_run_enabled 保持 true
2. 不需要重启任何进程：
   - 模拟 native tray（PID 22808 BigQMT_Simulation.exe）每 30 秒 tick 时
     重新读 strategy_runtime_policy.json，新配置立即生效。
   - 正式 native tray（PID 6996 BigQMT_Production_ReadOnly.exe）的
     RunSchedulerJobs 直接 if (Profile != "simulation") return;，根本不调 cycle。

## 自动交易机制（已经存在，无需新增代码）
- 调度源：tray/BigQMTAccountTray.cs 的 SimulationCycleIfDue 函数（30 秒 tick）。
- 触发条件（必须全部满足）：
  - StrategyPolicyEnabled() 返回 true（从 config JSON 读 v1_1_15_auto_run_enabled）。
  - 工作日（非周六日）。
  - 09:35 <= 当前墙钟时间 <= 14:50。
  - 当天还没跑过（lastExecutionCycleDate != today）。
  - 距离上次失败重试冷却已过。
- 执行内容：RunPython("run_v1_1_15_simulation_cycle.py", "--execute", 90000, ...)
  - 默认就 --execute，从来不需要人工批准参数。
- 订单逻辑（run_v1_1_15_simulation_cycle.py）：
  - 重新从 state_store 读最新 close-shadow 信号；
  - 对比当前 sleeve 持仓 vs 期望目标；
  - 若 signal 指向换仓（desired != current），单笔确定性订单提交；
  - 若信号为保持（reason = CURRENT_SCORE_INVALID_HOLD / NO_SWITCH / 风控等），
    不会下单，evidence 落盘 ALIGNED_NO_ORDER 或 PREFLIGHT_PASSED_NO_ORDER。
  - 若信号异常 / 阻塞 / 风控命中，按 fail-closed 处理，写 BLOCKED evidence。
- 风控内置在 v1.1.15 信号核心（v1_1_15_reproduction.py），不需要外部人工 gate：
  - MIN_HOLD_5（持有 >=5 天才能换）。
  - STOP_DAILY_DROP = -0.04（单日 -4% 即停损）。
  - STOP_DRAWDOWN = -5%（自最高 -5% 即停损）。
  - TAKE_PROFIT = +12%（+12% 即止盈）。
  - RISK_*_DIRECT_RANK 直接切到非 current 排名第一。
  - 重新对账 sleeve vs broker。

## 正式账户永不自动交易
- production_readonly profile 的 native tray 不调 cycle，
  只跑 HourlySnapshotIfDue、BridgeDailyRecordIfDue，都是 read-only。
- run_v1_1_15_simulation_cycle.py 顶端就 hard-bound ACCOUNT_ID = "90000001"，
  任何把它指向 90000002 的尝试都会被 raise SystemExit("blocked: simulation account binding mismatch") 终止。
- execution_admission.py 把 90000002 加入 deny 名单（reason = PRODUCTION_READ_ONLY）。

## Codex（我）的新角色
- 不再做"批准人 / gate"。
- 会做：异常告警分析、状态查询、报告、规划与文档。
- 不会主动调用 submit_order，更不会调用 _rpc_submit。
- 唯一保留的人工交互路径是 runtime_control.arm_simulation_strategy（120 秒授权窗口），
  但 cycle 已经默认 execute，仅在异常需要手动覆盖时才走那条路径。

## 已确认的运行时状态（2026-09-16 上午开盘前实测）

| 组件 | 状态 | 证据 |
|--|--|--|
| 模拟 native tray | RUNNING（PID 22808） | Get-Process |
| 正式 native tray | RUNNING（PID 6996） | Get-Process |
| Redis 6379 (模拟) | LISTEN（PID 9960） | Get-NetTCPConnection |
| Redis 6380 (正式) | LISTEN（PID 20604） | Get-NetTCPConnection |
| Dashboard 17890 (模拟) | LISTEN + 返回 sleeve 数据 | Invoke-WebRequest /api/status |
| Dashboard 17891 (正式) | LISTEN | Get-NetTCPConnection |
| 大QMT Bridge (模拟) | PONG + allow_order_methods=true | v1_1_15_cycle_20260916_072938.json |
| 主开关 | true | strategy_runtime_policy.json |
| 刹车列表 | []（已清空） | strategy_runtime_policy.json |

## 用户后续视角要看的不是"我是否批准了"，而是"托盘跑没跑、跑了什么"
1. 打开模拟看板：http://127.0.0.1:17890/simulation/strategies
   - 路由"策略账户"会列出 sleeve 净值曲线（含 NAV / return_rate / 持仓）。
2. 看 evidence：runtime_data/evidence/simulation/strategy_execution_cycles/
   - 今天 14:50 收盘后会落 v1_1_15_cycle_20260916_*.json，里面有
     execute_effective、status、signal.reason、
     sleeve.net_asset_value、sleeve.return_rate、
     orders_enabled_after 等字段。
3. 看 native tray 心跳：runtime_data/audit/simulation/native_tray.jsonl
   - v1_1_15_cycle_auto、v1_1_15_cycle_auto_blocked、v1_1_15_cycle_auto_retryable。
4. 看券商委托 / 成交：http://127.0.0.1:17890/simulation/orders

## 如果希望暂停自动交易
两种途径任一即可（任一都生效）：
1. native tray 菜单：右键通知区蓝色 S 图标 → 取消勾选"启用 v1.1.15 模拟策略运行"。
2. 改 JSON：config/strategy_runtime_policy.json 里
   simulation.v1_1_15_auto_run_enabled = false，下次 tick（<=30s）即停。

## 风险提示
- 自动交易意味着一旦风控 / 信号逻辑 / sleeve 对账出问题，会自动反映到委托上。
  当前 sleeve 对账（reconcile_daily_positions）和 admission gate（execution_admission.py）
  都已 fail-closed，但任何规则突破都会立即下单。
- 09-16 当天大概率触发换仓信号：
  - 09-14 close shadow: best=159985（已 MIN_HOLD_5）
  - 09-15 close shadow: best=162411 但 SMA4 没过（hold_days=4，09-16 收盘满 5 天）
  - 09-16 close shadow: MIN_HOLD_5 解除，162411 SMA4 几乎必然转正
    （仅需收 > 1.018 即 +0.3%），大概率信号变 CURRENT_SCORE_INVALID_BEST_SMA4
    换到 162411.SZ 油气 LOF。
  - 这笔委托会在 09-16 14:50 之前的某次 30 秒 tick 内自动 submit（前提 QMT 当时在线）。
  - 若 QMT 在 09:35–14:50 之间掉线，cycle 会进入 retryable 分支并 10 分钟后再试；
    收盘后若仍未成功，今天落 BLOCKED，不补单。

