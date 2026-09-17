# 项目进度

更新时间：2026-09-16

当前阶段：M01 可移植配置与合同已通过；M02 Coordinator 核心已收口；M03 Host Agent / M04 舰队监控 / M05 OpenClaw 只读继续；.121 Coordinator 已上线只读 fleet/progress 投影（30%）

## v1.1.15 模拟盘下单闸门放开（2026-09-16）

按用户明确指示「保持 v1.1.15 延续以前策略、保留下单换仓能力」，把 `config/strategy_runtime_policy.json` 里的
`simulation.v1_1_15_preflight_only_dates` 由 `["2026-09-16"]` 清空为 `[]`。这是本次唯一的改动点。

没有改动策略本身：信号、袖套、ETF 池、5 日持有期、排序口径全部原样，`strategy_registry.json` 中
`S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15` 仍为 `execution_enabled=true`、`broker_order_authority=SIMULATION_90000001_ONLY`、
`formal_execution=FORBIDDEN`。正式账户 90000002 依旧只读。

窗口与幂等约束不变：`src/kitling_bigqmt/simulation_cycle.py` 的 09:35–14:50（Asia/Shanghai）有界窗口、每个信号日
单次确定性 attempt claim、响应或超时后立即回锁 `READ_ONLY_LOCKED` 都继续生效。

live 证据：2026-09-16T07:29:38+08:00 手动预检返回 `BLOCKED: outside bounded simulation execution window`，
且在 claim 之前返回，未消耗今日那次真实执行（证据文件 `runtime_data/evidence/simulation/strategy_execution_cycles/v1_1_15_cycle_20260916_072938.json`）。
托盘会在 09:35 后执行一次 `scripts/run_v1_1_15_simulation_cycle.py --execute`。

## 托盘每小时只读快照修复（2026-09-16）

开盘前体检发现 `bridge_snapshot` DEGRADED：最新持久化快照仍是 2026-09-14T17:00:05+08:00（约 38 小时前），
但 Bridge 只读 ping 正常返回（281ms），说明不是 QMT 里桥接策略的问题。

根因：每小时账户快照任务只存在于已退役的 PowerShell 托盘（`tray/BigQMTTray.ps1` 的
`Invoke-HourlyAccountSnapshotIfDue`）。2026-09-15 重编的原生 .NET 托盘只保留了 09:35 执行周期、15:35 收盘影子、
16:10 数据湖、16:20 每日记录，唯独漏了每小时快照，因此 9/14 之后没有任何进程再写快照。

修复：`tray/BigQMTAccountTray.cs` 新增 `HourlySnapshotIfDue`，在 `RunSchedulerJobs` 的「仅模拟盘」闸门之前调用，
`TryRunScheduler` 也不再对只读档案提前返回。该任务只调用 `scripts/run_readonly_snapshot.py`（经 Bridge 只读读取
账户/持仓后落库，`broker_call_made=false`），不触碰任何下单路径；正式只读账户保留该任务，因为它是纯读账户事实。

验证：两个原生 EXE 于 2026-09-16T07:23+08:00 重新编译并重启；07:24:34Z / 07:24:35Z 两档案均写出
`hourly_account_snapshot` PASSED；`scripts/check_tray_health.py` 两档案 overall HEALTHY、bridge_snapshot PASS；
完整回归 210 passed（23.61s）。orders_enabled 仍为 false，运行时控制仍为 READ_ONLY_LOCKED。

新 EXE 哈希（`tray/BigQMT_native_tray_checksums.sha256`）：模拟 E2B252DC75C115B19EED4780A11C3C805AE8BA5DA38E33637AADBF8C0923310A，
正式 1357202158C1550A3DF74DC1F3327CA37871D00E8D89C1760B740C469210E8A9。

## M03 下单准入闸门收口（2026-09-15）

新增 `src/kitling_bigqmt/execution_admission.py`：所有本地下单路径必须先通过的唯一 fail-closed 准入闸门。
正式账户 90000002 无条件拒绝；本地运行控制窗口必须已 arm、未过期、且账户与策略都匹配；Coordinator 只读
执行候选预览必须指定本机为可执行主机，Coordinator 不可达即拒绝；即使传入合法租约信封也只做审计，当前里程碑
仍不能打开下单（LEASED_EXECUTION_NOT_ENABLED_IN_M03）。

三个真实下单入口全部接入闸门，且都在写任何 RPC 请求之前调用：`scripts/run_v1_1_15_simulation_cycle.py`、
`scripts/submit_v1_1_15_simulation_entry.py`、`scripts/run_one_time_510300_simulation_test.py`。

新增 `tests/test_execution_admission.py` 16 项，其中包含「三个入口都必须调用闸门」的防绕过断言与
「Coordinator 不可达不产生订单」断言。完整回归 208 passed（18.30s，py -3.12 -m pytest -p no:qt -q tests），
无 QMT/Redis 下单或撤单调用。

本轮未扩大订单能力：orders_enabled 仍为 false，Bridge execution_consumer_enabled 仍为 false，运行时控制依然在
finally 中回锁；overall_verified_percent 维持 30%，M03 仍为 IN_PROGRESS。

本轮已收口：C# 托盘（`tray/BigQMTAccountTray.cs`）新增只读「Intents」菜单行，复用
`scripts/probe_host_agent_intent_preview.py`（已改为零参数可用，Coordinator 不可达时输出 DEGRADED 只读信封并以
exit 0 退出，绝不打开执行权），仅在状态签名变化时写 `coordinator_intent_preview` 审计。该行不参与图标/state 判定，
只读预览失败只降级这一行文字，不会让健康账户误报红色。两个原生 EXE 已于 2026-09-15T21:36:28+08:00 重新编译
（360 已放行 `C:\BigQMT\work`），编译后复核哈希与 `tray/BigQMT_native_tray_checksums.sha256` 一致。

live 证据：2026-09-15T13:36:48Z 模拟托盘写出 `coordinator_intent_preview` → `empty_readonly; readonly=true;
orders_enabled=false`；本轮正式托盘 90000002（只读）重新启动后同样写出 `coordinator_intent_preview` →
`empty_readonly`，并自动补拉 Redis 6380 与看板 17891（由不可达转为监听）。两个托盘状态行均为
「在线; Redis 正常｜看板 正常｜订单锁定」。完整回归 210 passed（21.73s，py -3.12 -m pytest -p no:qt -q tests）。

M03 剩余待收口项：Host Agent 执行租约仍为 `LEASED_EXECUTION_NOT_ENABLED_IN_M03`（本里程碑不开租约、不下单）。

## M02 Coordinator 核心门禁收口（2026-09-15）

- 新增 tests/test_coordinator_core.py::test_two_fake_hosts_cannot_hold_valid_lease_simultaneously：两个独立
  CoordinatorStore 句柄共享同一 SQLite 文件，以 host-105 / host-125 竞争同一账户租约，current_lease 仅指向
  最新 host，fencing token 递增 (n -> n+1)，旧租约 validate_lease 与 preview_intent 均抛 StaleLeaseError。
- tests/test_coordinator_core.py 由 5 passed 增至 6 passed；M02 gate「两个 fake host 永远不能对同一账户同时
  持有有效 executor lease」达成，状态由 IN_PROGRESS 收口为 PASSED（weight 15）。
- progress/multi_host_program.yaml：overall_verified_percent 15% → 30%，status 更新为
  M03_M05_READONLY_FLEET_HOST_AGENT_IN_PROGRESS，updated_at 2026-09-15T19:05:00+08:00。
- tests/test_coordinator_bootstrap.py 进度断言同步至 phase 前缀 M03_ / 30%。
- 完整项目回归 179 passed（16.29s），无 QMT/Redis 下单或撤单调用。
- 已通过免交互 SSH（SSH_ASKPASS + scp + sudo -S）将 multi_host_program.yaml 部署至 192.0.2.121。在线实测
  /api/v1/progress 返回 M03_M05_READONLY_FLEET_HOST_AGENT_IN_PROGRESS / 30% / orders_enabled=false。远程备份
  /opt/bigqmt-coordinator/backups/20260915_190600_before_m02_close/。
- 证据见 docs/136_m02_coordinator_core_gate_acceptance_2026-09-15.md。

## Coordinator 只读 fleet/progress 投影上线（2026-09-15）
- 修复 serve.py 的 _scan_program_yaml 顶层键扫描 bug（原实现 strip 后匹配 status:，会被缩进的里程碑状态覆盖成 NOT_STARTED），改为仅匹配列首（column-0）键，并补采 updated_at。
- 本地 response_payload 完成 /api/v1/progress（返回真实 program phase + overall_verified_percent + updated_at，readonly:true / orders_enabled:false）与 /api/v1/fleet（hosts + executor_preview + intent_preview + progress，control=READ_ONLY_FLEET_PROJECTION）。
- 依赖免交互 SSH（SSH_ASKPASS + scp + sudo -S）部署到 192.0.2.121；systemd active，/healthz 200。在线实测 /api/v1/progress 返回 M01_M04_READONLY_FLEET_IMPLEMENTATION_IN_PROGRESS / 15% / 2026-09-15T16:10:00+08:00；/api/v1/host-agent/intent-preview-status 由 404 变为 200；/api/v1/fleet 200。
- 新增 3 项 pytest（progress 快照、progress 端点、fleet 投影），Coordinator 相关子集 25 passed。
- 备份：/opt/bigqmt-coordinator/backups/20260915_184137_before_fleet_projection/ 与 20260915_184500_before_updated_at_fix/。
- 安全边界不变：全链路 readonly / orders_enabled=false；prod 90000002 仍只读；无租约写入、无下单。证据见 docs/135_m04_fleet_projection_and_progress_endpoint_deployed_2026-09-15.md。M02/M04 仍 IN_PROGRESS，verified 维持 15%。

## M01 entry-point rollout 收口（2026-09-15）

- `portable_deployment.py`、v1.1.15 运行/回测/诊断脚本及缓存检查脚本的缺省配置统一经
  `machine_config.load_gateway`；显式 `--config` 仍可用于审计和复现指定配置。
- `load_tray_profiles` 负责便携部署检查中的托盘路径、Redis 端口和 QMT 根目录覆盖，
  machine.local.json 成为本机唯一覆盖入口。
- `py -3.12 -m compileall -q src scripts` 通过；针对性 M01/托盘测试 26 passed；
  之后完整项目回归 175 passed，未调用 QMT/Redis 下单或撤单接口。
- M01 gate 已达成，整体专项验证进度由 5% 更新为 15%。

## M01 machine.local.json 单点覆盖验收（2026-09-15）

- 已补齐 machine.local.json 单点覆盖验收链：validate_machine_local / effective_config /
  effective_config_hash / audit_hardcoded_paths，以及权威加载器 load_gateway /
  load_tray_profiles / load_qmt_paths / apply_data_lake_root。
- py -3.12 -m pytest -q tests/test_machine_config.py tests/test_machine_config_audit.py 14 passed；
  Coordinator 关联回归 17 passed。
- scripts/verify_machine_local_config.py 实跑：machine_local_valid=true，simulation/production_readonly
  两个有效配置哈希确定，双账户 orders_enabled=false，硬编码审计 finding_count=94。
- 证据：docs/134_m01_machine_local_single_point_override_acceptance_2026-09-15.md、
  runtime_data/evidence/simulation/machine_local_gate_20260915T145419+0800.json。
- M01 保持 IN_PROGRESS：运行时 loader fail-closed 语义已按方案 B 落实——存在但非法的
  machine.local.json（非法 JSON 或非对象）硬失败抛出 MachineLocalConfigError，缺失文件仍回退 {}；
  machine_config/audit/fail-closed 共 21 passed。仅剩 entry-point 统一化推行未收口。

## 开发期本机主执行、稳定后迁移（2026-09-14）

- 用户确认开发期间由本机 `192.0.2.105` 同时作为开发机、长期运行机和唯一模拟
  `ACTIVE_EXECUTOR` 候选；现有 F 盘 BigQMT 与两套 QMT 目录不变。
- `192.0.2.121` 继续只承担 Coordinator/Agent Gateway；`192.0.2.125` 改为稳定后的首选迁移
  目标，`198.51.100.113` 为后续备用只读节点。
- 迁移顺序改为先完成 105 闭环与稳定性，再让 125 只读接入、冻结/对账、人工迁移执行权；之后才
  演练 125→113。正式账户仍保持只读。本次仅记录决定，详见 `docs/121_development_host_primary_execution_and_later_migration_decision_2026-09-14.md`。

## 多主机 QMT/OpenClaw/Coordinator 总体确认稿（2026-09-14）

### M01/M02 首批实现（2026-09-14）

- 已新增 `src/kitling_bigqmt/coordinator_core.py`：纯本地、无 QMT/Redis/网络依赖的 Coordinator 控制面核心。
- 已实现 SQLite WAL、主机心跳、账户单一租约、递增 fencing token、`coordinator_epoch`、订单意图 preview/confirm 和审计事件。
- 已新增 `config/coordinator.example.json`，明确 `.121:18443`、模拟账户执行开关和正式账户只读边界。
- `tests/test_coordinator_core.py` 3/3 通过：双主 fencing、正式只读拒绝、epoch 重启失效。
- 本批未连接 QMT、Redis、OpenClaw，未修改托盘和订单权限；下一步为候选 Ubuntu/systemd 只读部署包。
- 已补充 Fake Host 心跳/接管测试；租约读改写使用 `BEGIN IMMEDIATE`，避免双主竞态。
- Coordinator 核心测试现为 5/5 通过；下一步生成 Ubuntu 24.04 预检与 systemd 候选包。
- 已生成 `scripts/coordinator/serve.py` 只读 bootstrap、Ubuntu 预检脚本、systemd 单元和部署说明；尚未复制或安装到 192.0.2.121。
- 已生成 `ufw_allowlist.sh`：内网最小放行 `.105 → .121:18443`，`.125/.113` 规则暂不启用；脚本仅供审核，尚未在 `.121` 执行。
- 已生成 `install_tailscale_ubuntu.sh`；官方安装、开机启动和交互式 `tailscale up` 均封装，因本机无 `.121` SSH 密钥尚未远程执行。
- 已通过 SSH 在 `192.0.2.121` 安装 Tailscale `1.102.4`，认证已完成；分配 Tailscale IP `100.86.46.78`，本机 ping 延迟约 3ms，Tailscale SSH 与 `tailscaled=active` 验证通过。
- 已通过 Tailscale SSH 部署只读 Coordinator bootstrap；systemd `active`，`http://192.0.2.121:18443/healthz` 返回 200。证据：`runtime_data/evidence/network/coordinator_bootstrap_192_168_1_121_20260914.json`。
- 用户决定当前不配置私有 CA/私有云；Coordinator 暂以内网 HTTP 只读 bootstrap 运行，管理访问优先走 Tailscale，HTTPS 延后至 OpenClaw/Host Agent 接入前。
- `.121` `/healthz`、`/readyz`、`/api/v1/progress` 均从本机访问返回 200；新增 `host_agent_snapshot.py` 只读心跳边界及测试，未连接真实 Host Agent。
- 新增 `host_agent_client.py` outbound 只读客户端；首版强制 `HEALTHY_READONLY`，只 POST 心跳到 `/api/v1/hosts/heartbeat`，7 个相关测试通过；尚未接入托盘或真实 QMT。
- `.121` bootstrap 已更新并重启；`192.0.2.105` 通过真实客户端发送只读心跳返回 `202 accepted`，`/api/v1/hosts` 可读取最近主机状态。
- 已在隔离 PyInstaller 环境完成两个新版 onedir 托盘构建；现有根目录 EXE 未替换。输出位于 `tray/BigQMT_模拟盘_90000001/` 与 `tray/BigQMT_正式只读_90000002/`，待启动烟测通过后再制作正式发布布局。
- 已整理隔离候选发布包 `dist/tray_candidate_20260914/`，含模拟/正式只读启动器和回滚说明；原根目录启动器保持不变。
- 候选托盘实际启动暴露 pywin32 `Shell_NotifyIcon` 句柄类型错误；已修复为保存并复用 `PyHANDLE` 图标句柄，待重新编译候选 EXE。
- 已重新编译并更新候选包；模拟盘候选托盘实际启动后持续运行，`.121 /api/v1/hosts` 收到最新只读心跳，`sent_at=2026-09-14T09:32:33Z`。
- 针对用户截图再次修正通知结构（ID 字段保持整数 0、句柄仅在 hIcon 字段）；修正版实际启动验证通过，最新心跳 `sent_at=2026-09-14T09:48:09Z`，未再出现 `PyHANDLE` 异常。
- 再次确认不同 pywin32 对 `NIM_MODIFY` 兼容性不一致，已彻底移除账户托盘运行期 `NIM_MODIFY`；旧模拟 EXE 已备份至 `deploy/backups/20260914_before_tray_handle_fix/`，根目录模拟 EXE 已替换为无该调用的 onefile 修正版。

- 已形成覆盖架构、机器职责、源码/Windows/Ubuntu/NAS 目录、MCP+Skill、唯一执行权、迁移、测试、
  发布、回滚和进度查询的总规划：`docs/120_multi_host_qmt_openclaw_coordinator_master_plan_2026-09-14.md`。
- 项目阶段新增 P24–P28；专项使用 `progress/multi_host_program.yaml` 记录 M00–M08、权重和确认点。
- 专项当前严格验证进度为 5%：架构和网络基线已通过；现有 Bridge/Tray/核算代码只有完成多主机适配
  和证据门禁后才计入专项进度。
- 等待用户 AP1 确认后，先推进 machine.local v2、协议合同和本地 Fake Agent Coordinator 测试；
  未经 AP2 不在 `192.0.2.121` 安装服务，未经 AP5 不启用 OpenClaw 模拟订单意图。

## V2 单一实施确认稿（2026-09-14）

- 后续以 `docs/122_multi_host_bigqmt_implementation_plan_v2_2026-09-14.md` 为唯一实施顺序：105 开发并
  作为当前模拟主力执行候选，121 使用 `https://192.0.2.121:18443/`，125/113 的多 Agent OpenClaw
  从 NAS release 本地安装，只有用户指定 agent_id 可在 AP5 后取得模拟订单 scope。
- 旧文档保留设计和证据来源；与 V2 实施顺序冲突时，以 V2 为准。当前仍等待 AP1，不改变运行状态。
- 用户已决定 Coordinator 初期通过 `https://192.0.2.121:18443/` 访问，DNS 与公网/overlay 接入后置；
  初期仅开放开发机到 121 的最小 HTTPS 路径，证书使用 IP SAN `192.0.2.121`。
- OpenClaw 已部署于 125/113 且为多 Agent 模式；后续从 NAS 发布源安装 MCP+Skill 到各主机本地目录。
  用户指定的单一 `agent_id` 才能取得独立的 `executor_simulation` scope，其余 Agent 仅观察/报告。
- 用户已确认 Agent 映射：113 为 `chief`→`execution`，125 为 `kitling`→`xiaocai`。两个下游 Agent
  均登记为不同主机的候选执行身份；AP5 时仍只能选择一个作为当前模拟账户手机订单入口。详见
  `docs/126_openclaw_multi_host_agent_registry_decision_2026-09-14.md`。
- 已将 V2 规划、MCP/Coordinator 说明、OpenClaw 多 Agent inventory 请求和 SHA256 清单复制到
  `\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\reports\planning\2026-09-14_coordinator_openclaw_v2`；
  该目录仅供阅读和回传非敏感 Agent 信息，不构成部署或订单授权。

## P19/P21 OpenClaw MCP/Skill 与 Coordinator 121 验证（2026-09-14）

- OpenClaw 最终交付确定为“中央 BigQMT MCP Server + `bigqmt-operator` Skill + 安装/验证包”；Skill
  只描述工作流，MCP 才提供类型化查询和订单意图工具，凭据不进入 Skill 或发布包。
- Coordinator 采用与宿主无关的稳定 URL、Python wheelhouse + venv + systemd 可迁移包；活动状态保存在
  本机 `/var/lib`，迁移时冻结租约、备份、停止旧实例、递增 epoch 后才启动新实例，禁止 NAS SQLite
  和新旧双主。
- 已通过 SSH 只读验证新 PVE Ubuntu `192.0.2.121`：Ubuntu 24.04.4、4 vCPU、7.7 GiB 内存、
  108 GiB 可用盘、Python 3.12.3、systemd/NTP 正常；能反向访问开发机、两台 QMT 候选机和 NAS。
- 当前 121 未安装 Docker/Podman/curl，也未安装 Coordinator；证据与实施计划见
  `docs/119_openclaw_mcp_skill_and_portable_coordinator_plan_2026-09-14.md`。

## P19/P21 长期 QMT 主机、OpenClaw 与网络评估（2026-09-14）

- 硬件评估仍认为物理 Win11 `192.0.2.125` 适合作为未来迁移目标，ESXi-C Win11
  `198.51.100.113` 适合作为备用只读节点；实际部署顺序已更新为开发期由 `192.0.2.105` 主力运行，
  稳定后再人工迁移。OpenClaw 分别运行于 WSL/Windows 不改变 QMT 必须由 Windows Tray 独立运行的边界。
- 手机端可以经 OpenClaw 查询和提交结构化订单意图，但 OpenClaw 不得直连 QMT、Redis、SQLite 或
  通用下单函数；中央 Agent Gateway/Coordinator 与本机 Execution Engine 必须逐层鉴权和复核。
- 从开发机 `192.0.2.105` 实测两台 QMT 候选机、NAS、PVE/ESXi 和 `10.10.10/10.10.11` 主要节点
  均可达；`192.168.1.110` 无响应，ESXi-C 宿主因管理 IP 未知未测。当前证据只覆盖开发机单向探测。
- `http://198.51.100.113:18789/` 可从跨网段局域网取得明文 HTTP `200 OK`，需要优先审计 OpenClaw 的
  绑定、认证、TLS 与 allowlist；两台候选
  QMT 主机的 Redis、Dashboard 和 58600 均未对开发机开放。
- PVE2 新建独立小型 Ubuntu VM 仍是本地 Coordinator/Agent Gateway 推荐宿主。详见
  `docs/118_qmt_host_openclaw_and_lan_assessment_2026-09-14.md` 与
  `runtime_data/evidence/network/lan_connectivity_20260914_1146.json`。本次未改变运行与订单状态。

## P19/P21 可迁移配置与双机唯一执行权记录（2026-09-13）

- 本机 BigQMT 与两套 QMT 继续使用现有 F 盘目录；其他 Windows 运行机默认使用
  `E:\kitling_bigqmt`、`E:\国金QMT交易端模拟` 和 `E:\国金证券QMT交易端`。
- `config/machine.local.json` 将扩展为每台机器唯一的路径、端口及 Coordinator 端点覆盖文件；
  密码、服务密钥、策略准入和正式下单授权继续独立保存，不能由机器配置开启。
- 同一账户允许两台 QMT、Tray 和 Bridge 在线，但只能有一台 `ACTIVE_EXECUTOR`；其他机器必须为
  `STANDBY_READONLY`。执行权按账户使用短租约和递增 fencing token，失联时失败关闭。
- NAS 仅承担版本发布、备份和审计副本，不使用 SMB 文件锁仲裁下单权。
- Coordinator 宿主仍为 `PENDING_SELECTION`：独立 Ubuntu 小主机、ESXi Ubuntu 和国内云 VPS 为
  主要候选；Cloudflare Durable Objects 为待验证候选。Tailscale/Cloudflare Tunnel 仅作为网络层。
- 当前只冻结设计，没有启动 Coordinator、修改 QMT/Bridge/Tray 或改变任何订单开关。详见
  `docs/115_portable_multi_host_coordinator_decision_record_2026-09-13.md`。

## BIGQMT_BRIDGE 统一候选发布（2026-09-09）

- 已实现 `BIGQMT_BRIDGE` 候选入口及统一订单/撤单准入层；模拟和正式环境使用同一份桥接代码，
  后续环境放行不需要修改桥接逻辑；
- 两个环境仍必须使用物理隔离的 QMT 部署目录、本机私有配置、Redis 命名空间与账号标识；
  当前两份默认配置均为锁单；
- 模拟下单未来需要环境、账户、策略袖套、预检、parity、显式确认与执行消费同时通过；正式盘还需
  已验证模拟验收及用户单独批准；
- 当前 QMT 正在使用 `BIGQMT_REDIS_DRYRUN`。候选 `BIGQMT_BRIDGE` 尚未部署，不得与旧策略
  并行消费同一 Redis 请求通道；部署将先做只读回归。详见
  `docs/15_bigqmt_bridge_unified_release_2026-09-09.md`。
- 本机自动测试累计 **33/33 通过**；未调用 QMT 下单或撤单接口。

## RC3 双环境完整能力候选包（2026-09-09）

- 已生成 `kitling-bigqmt-bridge-20260909-rc3`：模拟和正式包共用完整 Bridge 代码，未来放行不需要改 QMT Bridge 源码；
- 正式环境仅在本机私有 profile 绑定了脱敏账号 `8890****6688`，以便错误登录时失败关闭；这不是正式下单授权；
- 正式 Redis 固定为 `127.0.0.1:6380/0`，同时对正式 RPC 额外应用严格只读方法白名单；下单/撤单未暴露；
- 33/33 本机自动测试通过，两个 ZIP 的 59 项文件清单与 SHA256 已复核；未调用任何 QMT 下单或撤单接口；
- RC3 尚未部署到任一 QMT。P06 parity 和正式盘独立放行仍为 `BLOCKED`。

## 双环境 QMT Bridge 只读实测（2026-09-09 10:35）

- 模拟 Bridge：账户、5 个持仓、空委托/成交及实时行情读取通过，订单 RPC 继续关闭；
- 正式 Bridge：账户、1 个持仓、空委托/成交及 `511880.SH` 实时行情读取通过，订单 RPC 继续关闭；
- 正式 Redis 实际运行于独立端口 `127.0.0.1:6380` 的 DB 5，已把主机配置同步为该事实；
- 正式只读快照 run id：`0f20476b2f7d4adaaa6aaaeb60b8844b`。这完成 P02/P03 的正式只读连通性证据，
  不改变 P06/P12/P15 的订单门禁。

## P06-A / P06-B 快速推进（2026-09-09 10:53）

- 刷新 P06 artifact-only 审计：3/6 检查通过；7 个冻结排除已解释，12 个资格/数据差异和 6 个分数差异仍待逐证券证据；
- 新增 parity 闭环计划 `docs/17_p06_v1_1_15_parity_closure_plan_2026-09-09.md`，保持 v1.1.15 信号冻结；
- 本地 Dry-run 复验通过：即使输入伪造为正式、订单开启、parity 全通过，项目级 BLOCKED 仍拒绝，未调用 QMT/Redis 订单接口；
- 自动测试仍为 **33/33 通过**，`BIGQMT_BRIDGE` 未修改。

## P07 只读对账启动（2026-09-09 11:02）

- 用户决定不再重建 PTrade 逐证券证据；该差异登记为研究限制，不宣称跨引擎完全 parity；
- P06-B 离线预检已完成，但 P06 真实模拟订单门禁仍为 `BLOCKED`；
- 模拟端对账：前后快照无持仓变化，委托/成交均为 0；reconciliation id `d84cb06f63254c5898c7dfd424094659`，记录于 SQLite WAL 与当日快照审计；
- 正式端只读对账：前后快照无持仓变化，委托/成交均为 0；reconciliation id `454cd1eb87ef4e2692add71eb075d11c2`，记录于 SQLite WAL 与当日快照审计；
- 项目阶段推进为 `P07_RECONCILIATION / IN_PROGRESS`，下一步建立策略袖套基线与对账报告。

## P07 外部基线与策略袖套初始化（2026-09-09 11:08）

- 模拟账户 5 个已有券商持仓全部登记为外部基线，未自动认领给策略；
- v1.1.15 独立袖套已注册，初始资金/现金/净值均为 100,000 元，策略归属持仓与成交均为 0；
- `券商总持仓 = 外部基线 + 策略归属持仓` 校验通过；
- 详见 `docs/19_p07_simulation_external_baseline_2026-09-09.md`；下一步进入 P08 信号到袖套的离线重放。

## 2026-09-09 11:16 — P08 信号到策略袖套无订单回放

- 已完成一轮近期 QMT 只读行情到 v1.1.15 信号状态机的回放，证据见 `docs/20_p08_v1_1_15_signal_to_sleeve_dryrun_2026-09-09.md`。
- 覆盖 25 个证券、18 个交易日、11 条信号、2 条虚拟状态推进；`563230.SH` 有一次只读行情超时，因此仅标记 ATTENTION。
- 已生成 `staging/dryrun/p08_v1_1_15_signal_candidate_20260904.json` 并通过项目级 dry-run 入口验证；当前 `preflight=BLOCKED`，候选被安全拒绝，未记录可执行意图，也未调用 QMT 下单/撤单。
- 模拟与正式只读环境已再次恢复核对，持仓变化为空，订单/成交均为 0。
- P07 已标记 PASSED，P08 进入 IN_PROGRESS；下一步为 P09 多策略袖套注册、外部基线隔离和净值/收益统计。

## 2026-09-09 11:22 — P09 多策略袖套初始化

- 已登记策略 A（10 万）和策略 B（100 万）两个模拟袖套；A 重复登记返回 `DUPLICATE`，资金不会被重置。
- 模拟账户现有 5 个券商持仓仍是 external baseline，不自动归属任一策略；`broker = external baseline + strategy_owned` 核对通过。
- 两个袖套当前 NAV 分别为 100,000 / 1,000,000，收益率均为 0%，无策略持仓、无策略成交。
- 已增加 `sleeve_nav_snapshots` NAV 时间序列表及幂等写入/曲线查询；A/B 各已记录首个 NAV 点。详见 `docs/21_p09_multi_strategy_sleeve_registry_2026-09-09.md`。
- P09 已标记 PASSED；下一步进入 P10 只读 Dashboard 数据契约（不在本轮扩展 Dashboard 页面样式）。

## 2026-09-09 11:36 — P10 Dashboard 数据契约

- `/api/status` 的只读投影现在包含账户快照、`strategy_sleeves`、每个袖套的当前 NAV/收益和 `nav_series`。
- 页面和 API 都不暴露下单、撤单或确认入口；`read_only=true`、`orders_enabled=false`、`order_actions_exposed=false` 固定保留。
- 缺少估值价格时返回 `VALUATION_UNAVAILABLE`，不使用零价格伪造收益。
- 详见 `docs/22_p10_dashboard_data_contract_2026-09-09.md`；下一步做 loopback 页面渲染验证。

## 2026-09-09 11:43 — P10 loopback 验证

- 已重启本机 Dashboard 并验证 `http://127.0.0.1:17890/healthz`、`/api/status`。
- API 返回 2 个策略袖套，UI 袖套渲染脚本已加载；只读和订单锁定字段均正确。
- P10 页面暂保持现有简洁样式，只增加策略袖套表格和 NAV 点数展示；详细视觉改版留到后续。
- 下一步进入 P11 数据湖接入契约。

## 2026-09-09 11:55 — P11 数据湖导出

- 已完成 SQLite WAL → Parquet 的只读快照导出，DuckDB 直接读取校验通过。
- 数据分工已固定：Redis 实时总线、SQLite 运行权威、Parquet 归档、DuckDB 分析、QuestDB 延后评估、研究湖只作补充。
- P11 已标记 PASSED；P12 模拟交易验收继续保持 BLOCKED，原因仍是 P06 逐证券等价证据缺口，未调用任何交易接口。
- 详见 `docs/23_p11_readonly_snapshot_lake_export_2026-09-09.md`。

## 2026-09-09 13:10 — Dashboard 白底主题

- 已将 Dashboard 改为白底浅色风格，中文化状态信息，并把非交易时段从“错误”改成等待提示。
- Playwright 验证桌面 1440px、手机 390px 均无横向溢出和浏览器错误；策略袖套、NAV、安全状态正常显示。
- 详见 `docs/25_dashboard_light_theme_2026-09-09.md`；正式账户仍只读，模拟账户订单能力仍按交易时段门禁执行。
- Dashboard 侧边栏目前只作导航视觉展示，点击交互按用户要求延后到项目最后统一修复。

## 2026-09-09 13:18 — Dashboard 侧边栏导航修复

- 六个侧边栏项已支持点击和键盘 Enter/Space，并定位到对应看板区域。
- 委托/成交、行情健康度、审计与日志仍是只读展示，不增加任何交易接口。
- Playwright 逐项点击验证通过，浏览器控制台错误为 0。
- 详见 `docs/26_dashboard_sidebar_navigation_2026-09-09.md`。

## 2026-09-09 13:45 — P12 模拟交易前预检

- 模拟账户 `90000001` 最新只读快照通过：总资产 10,040,527.34 元、5 个持仓、0 委托、0 成交。
- 3 次行情采样全部通过，5/5 标的新鲜；本地 Dry-run 首次 `RECORDED/PLANNED`，重复请求返回 `DUPLICATE`。
- 未调用 QMT 下单/撤单，Bridge 写权限仍关闭；正式账户 `90000002` 继续只读。
- 详见 `docs/27_p12_simulation_preflight_and_dryrun_2026-09-09.md`；下一步需要明确单笔模拟验证订单参数。

## 2026-09-09 13:52 — 模拟持仓名称显示

- 已修复 QMT `stock_name` 编码损坏导致的乱码；新增本地显示映射，代码仍是唯一主键。
- 当前 5 个模拟持仓已在 Dashboard 显示名称、代码、数量、可用、价格和市值。
- 详见 `docs/28_simulation_positions_with_names_2026-09-09.md`。

## 2026-09-09 — BigQMT 托盘管家正式纳入规划

- 已新增 P14 托盘核心、P15 运行健康检查、P16 自动登录（延后）、P17 正式候选验收。
- 托盘管家负责启动/监控/日志/Dashboard，不直接下单；模拟和正式只读档案分别隔离。
- 详见 `docs/29_bigqmt_tray_manager_plan_2026-09-09.md`。

## 2026-09-09 14:20 — 规划核对与 Dashboard 产品轨道

- 核对确认：P10 已完成的是只读数据契约和单页展示，侧栏目前仅滚动到同页卡片；不存在六个可独立访问的 Dashboard 页面。
- 已新增 P18 Dashboard 产品研发：运行总览、策略袖套、账户持仓、委托成交、行情健康度、审计日志六个只读路由页面，以及模拟/正式只读环境隔离与页面级验收。
- 同时补入此前未进入阶段表的 P19 可移植部署升级、P20 备份/告警运维、P21 局域网只读观测、P22 策略准入治理、P23 数据湖调度与留存。
- 详见 `docs/30_project_scope_audit_and_dashboard_product_plan_2026-09-09.md`。

## 2026-09-09 14:32 — 模拟 Bridge 重新核对阻塞

- 用户确认已关闭 `BIGQMT_REDIS_DRYRUN`，并在模拟 QMT 启动 `BIGQMT_BRIDGE`；项目状态已记录为“用户声明、待只读 ping 验证”。
- 主机严格只读快照无法连接 `127.0.0.1:6379`；端口未监听且不存在 Redis 进程，因而不能将 QMT 界面“运行”视为 Bridge 运行就绪。
- 已新增 `SIMULATION_REDIS_BRIDGE_CONNECTIVITY` 活动阻塞。恢复模拟 Redis 后必须重新完成 Bridge/account/positions/orders/trades/quotes 只读预检；订单仍保持锁定。

## 2026-09-09 14:21 — 模拟 Redis / BIGQMT_BRIDGE 恢复验证

- 使用 Cygwin Redis 的 `/cygdrive/f/.../redis-simulation.conf` 路径恢复了模拟实例；`127.0.0.1:6379` 已监听。
- 新只读快照 `4137e92255884d168ab056d031456088` 成功：账户 `90000001`、5 个持仓、0 委托、0 成交、5 个行情对象；Bridge ping 返回版本 `0.3.26` 和 `allow_order_methods=false`。
- 14:20 的 3 轮行情检查中，5/5 ETF 全部 `FRESH`。恢复连通性阻塞已解除；订单锁不变。
- v1.1.15 遵循收盘信号、下一交易日执行，今日收盘后再生成完整信号证据；不得在未收盘时将盘口作为收盘信号。

## 2026-09-09 14:22 — v1.1.15 候选意图恢复复核

- 对历史候选 `p08-v1-1-15-20260904-162411-buy` 重新执行本地 Dry-run：已记录为 `PLANNED`，策略袖套资金、100 份整数手和门禁检查通过。
- 本次仅写入本地幂等审计，不调用 QMT 下单或撤单；`broker_call_made=false`。
- 运行时控制文件仍为 `READ_ONLY_LOCKED`：`orders_enabled=false`、`execution_consumer_enabled=false`。该候选为历史验证素材，不可作为 2026-09-09 的策略交易信号。

## 2026-09-09 14:46 — 模拟 Bridge 首笔柜台成交

- 用户明确授权模拟账户 `90000001` 对 `510300.SH` 买入 100 股后卖出。经账户空持仓/空委托核对、QMT 运行模式修正和模拟专用短时许可后，买入委托 `200` 全成 100 股；成交 `50055942`，成交价 4.640，手续费 0.1392。
- QMT 事实快照显示 `available=0`、`on_road_volume=100`，该 ETF 按 T+1 约束当日不可卖；未提交卖单、未重试买单。
- 动态订单锁及磁盘上的模拟配置已立即恢复关闭。当前运行的 Bridge 需下次停止/启动才会重新加载静态 `rpc_allow_order_methods=false`；在此之前动态锁已使新订单准入失败关闭。
- 该成交属于 `SIMULATION_510300_BRIDGE_TEST_20260909` 运行验证，不归属 v1.1.15 策略袖套。

运行边界已确认：未来 QMT 电脑只由 **BigQMT 托盘管家**运行完整策略、执行和监控链路；
Codex 仅用于开发、验证、审计和人工辅助，不进入运行、心跳或下单路径。详见
`docs/13_bigqmt_tray_runtime_boundary_2026-09-08.md`。

P06 artifact-only 门禁已汇总：PTrade 产物完整性、持仓重放、QMT 风控重放共 3 项通过；
逐日 best/score 全量一致性、12 个逐标资格/数据差异、4 个 QMT/研究湖来源差异尚未关闭。
因此状态为 `BLOCKED`（只阻塞订单意图，不阻塞只读诊断），证据见
`runtime_data/evidence/simulation/p06_artifact_only_gate_20260908_191158.json`。
不可覆盖状态快照：`progress/history/20260908_191353_p06_artifact_only_blocked.json`。

## 模拟 QMT 可用性中断（2026-09-08 20:53）

- 用户确认券商已断开模拟盘 QMT；
- 20:50 的只读 RPC 仍可读取模拟账户 `90000001`，订单/成交为空且 `allow_order_methods=false`；
- 20:52 执行 `scripts/run_readonly_snapshot.py` 时 Bridge `ping` 超时，未能写入新快照；
- 未调用任何订单或撤单接口，`orders_enabled=false` 不变；
- 实时行情、账户和 Bridge 验证暂停，等待用户确认重连后按 ping → 账户/持仓/委托/成交 → 行情新鲜度顺序恢复。
- 离线 PTrade 证据诊断、Dry-run 设计、单元测试和托盘规划可继续。

## 模拟 QMT 恢复（2026-09-08 21:00）

- 用户确认 QMT 已恢复后，`run_readonly_snapshot.py` 成功记录只读快照：模拟账户、5 个持仓、
  空委托、空成交和 5 个行情快照均可读；订单权限继续关闭；
- 当前为收盘后，5/5 行情时间戳超过交易时段 180 秒门槛，行情门禁按预期保持 `BLOCKED`；
  这不表示重新断线，也不允许订单意图；
- 下一交易时段先做行情新鲜度采样，再恢复依赖实时行情的只读验证。

## 离线 Dry-run 运行入口（2026-09-08 21:54）

- 已完成 `scripts/run_dryrun_from_json.py` 与项目级门禁运行器；它不信任输入 JSON 的环境、
  订单开关、预检或 parity 标记，而是强制使用 `progress/current_status.json`；
- 当前使用故意伪造为 production / `orders_enabled=true` / 全部 `ALLOWED` 的样本，仍被项目的
  `preflight=BLOCKED` 正确拒绝；未写拟订单，未调用 QMT；
- 本地测试累计 **19/19 通过**。当且仅当未来项目预检与 parity 都被独立放行为 `ALLOWED` 时，
  该入口才可能在本地 SQLite 记录 `PLANNED`；它永远不会直接调用券商接口。

## 多策略资金袖套离线核心（2026-09-08 22:12）

- SQLite WAL 已增加策略袖套、策略归属持仓、可归属成交三类权威表；
- 实现 A=100,000 与 B=1,000,000 独立资金、独立持仓、费用、已实现/未实现收益、净值与复利；
- 证券数量对账强制使用 `券商总数 = 外部基线 + 策略归属总数`，不会自动认领账户既有持仓；
- 离线测试通过，尚未接入任何 QMT 成交，未产生订单。详见
  `docs/14_strategy_sleeve_accounting_2026-09-08.md`。

## 当前推进（2026-09-08 17:46）

- 已准备独立的 PTrade v1.1.15 `SCORE_MATRIX` 诊断补丁和主机侧解析器；冻结基线源码未修改，补丁不会改变信号、冻结、状态、成交或订单逻辑。
- 解析器会按 UTF-16/GBK 等编码读取日志，要求每个诊断日包含 U25 的 25 条逐标记录，并在缺行、重复标的或字段缺失时标记 `INCOMPLETE`。
- 当前长期基线日志尚未包含 `SCORE_MATRIX`，解析结果为 `INCOMPLETE`；这符合预期，不将普通日志误当作逐标 parity 证据。
- 已核实 PTrade 当前目录实际只有 TXT 日志、交易详情 CSV、持仓明细 CSV 和两张 PNG；因此不再把“导出 SCORE_MATRIX”作为当前必需用户动作。现有产物可继续做 artifact-only parity，但不能替代逐标 `dypre` 证据。
- 已完成现有产物审计：TXT 2,077 个日志日、交易明细 5,281 行、持仓明细 2,429 行；持仓明细最后日期为 2026-09-02，和最近可重放成交日 2026-08-31 对齐后，持仓数量差异为 0。审计证据见 `runtime_data/evidence/simulation/ptrade_v1_1_15_artifact_audit_20260908_174546.json`。
- 新增解析器单元测试后，项目测试为 **14/14 通过**；Redis/QMT 仍保持只读，`allow_order_methods=false`，没有订单意图。
- 下一步改为：先用现有 TXT/CSV/PNG 完成可复现 artifact-only parity；逐标诊断补丁作为可选增强，不阻塞当前只读验证，但在证据缺口关闭前仍不释放订单意图。

已完成：

- 确认项目数据以 F 盘为长期存储目标。
- 完成模拟版/正式版 QMT 路径和进程的只读盘点。
- 确认 E 盘约 49.9 GB 可用，F 盘约 4.82 TB 可用。
- 发现两套 QMT 当前均有相关进程运行。
- 已记录用户更新后的 QMT 路径：
  - `C:\BigQMT\work\国金QMT交易端模拟`
  - `C:\BigQMT\work\国金证券QMT交易端`
- 已确认 F 盘 QMT 进程实际运行。
- 初始检查确认 Redis 6379 端口未监听，随后已启动项目模拟 Redis。
- 已创建项目运行数据目录和 Redis 8.10.1 MSYS2 运行包目录。
- 已写入模拟 Redis 配置，绑定 `127.0.0.1:6379`，持久化路径为 F 盘。
- 已启动本机模拟 Redis，`PING`、测试键写入和读取均通过。
- 已确认模拟 QMT 内置 `qmt_api`、`redis`、`pandas` 依赖存在。
- 已将参考 Bridge staging 到项目目录，并通过主机 Python 3.12 语法编译检查。
- 已将 Bridge 入口和核心包复制到模拟 QMT `python` 目录，尚未在界面加载。
- 已确认模拟 QMT 已把 `BIGQMT_REDIS_DRYRUN` 写入自身策略索引，并记录了启动尝试。
- 已确认 QMT 发起了 `SH000300` 日线行情请求并收到历史数据回调。
- 已完成一次只读运行测试，未调用下单接口。

进行中：

- 按 F 盘新路径验证 QMT 原生行情数据目录和运行环境。
- 处理 QMT 策略 `BIGQMT_REDIS_DRYRUN` 的 `parse error`，确认小型包装策略的加载方式。
- 已准备只包含回调导入和 `dryrun` 配置的小型 QMT 包装策略，等待在模拟盘编辑器加载。
- 首个导入式包装策略已在 QMT 以分钟线启动，但仍未产生 Bridge 输出；下一轮改用直接定义并转发 QMT 回调的入口。
- 原生 `QMT_LIFECYCLE_PROBE` 同样出现 QMT `parse error` 且未触发 `init/handlebar`；当前阻塞点确认为 QMT 新建 Python 策略的加载/解析链路，而非 Bridge。
- 正式版保留正常的内置 `PY简单示例.py` 源码；模拟版同名示例及 `_1` 副本已被 QMT 保存链路替换为同一单行令牌文本，内置示例也因此 `parse error`。等待用户决定是否仅恢复模拟版示例文件做对照验证。
- 在模拟 QMT 模型交易环境重新加载 Bridge，确认 QMT Python 运行时、Redis RPC 和版本信息。
- 收集并处理模拟版 QMT 当前无法登录的问题。
- 处理 Bridge 文件已复制但 QMT 界面策略列表不显示的问题（策略索引层已确认）。

尚未执行：

- 未修改 QMT 原生配置、账户或行情数据库；仅复制了待加载的 Bridge 文件到模拟版 `python` 目录。
- Redis 已启动；尚未接入大 QMT Bridge。
- 未复制 QMT 策略文件。
- 未连接账户、持仓、委托或成交接口。
- 未进行任何下单操作。
- 模拟版 QMT 当前无法登录，Bridge 验证暂时阻塞。
- 已确认 QMT 策略列表使用自身索引，不能仅靠复制文件期待自动显示。
- 已确认模拟版 `python\bigqmt_signal_trader\` 目录及核心文件完整；正式版未部署该包。
- 已确认 QMT 粘贴保存的策略由 `configFormula` 内部索引管理，不会自动回写同名 `.py` 文件。
- 当前模拟版依赖模块已恢复为入口所需的原始名称；QMT 编辑器生成的策略文件属于内部编码形式。
- 本次运行出现 `load file [BIGQMT_REDIS_DRYRUN] parse error`，随后策略停止。
- 本次没有发现 Bridge 启动标记或 Redis `bigqmt*` 业务键，Bridge 运行尚未验证。

下一道安全门：用户明确同意后，仅从正式版复制原始 `PY简单示例.py` 到模拟版做恢复性对照；在原生策略能触发回调前，不再加载 Bridge。

## P06 v1.1.15 复现推进（2026-09-08 12:50）

已完成：

- QMT 日线 DataFrame JSON 信封标准化，支持列式/行式返回；格式异常、重复日期失败关闭。
- U25 加 fallback 共 26 个标的从 2015-01-01 下载历史预热数据，2018-01-01 起生成探针。
- 已把 PTrade v1.1.15 的加权动量、SMA4、5% 换仓、最短持有、风控优先级、冻结期、
  pending target 和显式虚拟状态推进实现为主机纯函数；单元测试累计 12/12 通过。
- 已对比 PTrade 长期日志（327 条 RC1 signal）与 QMT `front` 探针（331 条），并固化
  `runtime_data/evidence/simulation/qmt_v1_1_15_signal_probe_20260908_123444_vs_ptrade.json`。

当前结论：v1.1.15 规则复刻核心已完成，但行情等价性未通过。QMT `front/back/none` 均不能
直接宣称等价 PTrade `fq='dypre'`；逐条信号仅 11 条完全匹配，差异从 2018-04 后开始明显。
因此没有接入拟订单规划器，没有调用 QMT 下单/撤单，正式盘仍未部署。

下一步安全门：取得或重建 PTrade `dypre` 逐日样本，区分复权因子/数据源差异与成交状态差异；
只有信号 parity 通过后，才继续 P06 的目标数量、手续费和部分成交 Dry-run。

## 逐日分数对齐诊断（2026-09-08 13:21）

已完成全周期 QMT `front` 与 PTrade RC1 日志的 best/score 对齐：2,029 个可评分日期中，
best 标的一致 2,010 个，PTrade best 分数一致 2,023 个。2018-04-24 等日期分数完全一致，
但此前信号探针因使用“次日 raw close 虚拟成交”提前推进持仓，导致最短持有期时序偏差。

当前下一步是用 PTrade 交易详情和日志重建实际成交/部分成交状态，再重放 QMT 信号。该工作
仍属于只读验证，未调用下单/撤单接口。

## PTrade 成交状态回放通过（2026-09-08 13:42）

已按时间顺序重放 v1.1.15 的 5281 笔成交，重建 653 个进出场事件和加权入场成本；PTrade
日志中的 2077 个盘后当前标的全部能在回放持仓中找到。此前“次日 raw close 虚拟成交”不再
作为 parity 依据。下一步用该真实状态重放 QMT 信号，订单开关继续关闭。

## 原始风险状态对齐通过（2026-09-08 14:00）

使用 QMT `none` 原始收盘和回放的真实入场成本，83 个风险触发日全部与 PTrade 日志一致：
单日跌幅、回撤、止盈优先级均通过。剩余差异只在普通动量排名及部分成交造成的最短持有
时序；在此之前不进入本地拟订单规划。

## 复权口径 A/B 结论（2026-09-08 14:10）

QMT `back` 全周期逐日分数结果与 `front` 完全相同，不能通过切换 QMT 前/后复权消除剩余
排名差异。下一步针对少数差异代码检查历史数据源和复权因子；订单仍关闭。

## v1.1.15 排名差异分类（2026-09-08 14:08）

已把剩余差异固化为审计报告
`runtime_data\evidence\simulation\qmt_v1_1_15_rank_difference_diagnosis_20260908_140836.json`：
19 个普通 best 标的不一致中，7 个是 PTrade 主策略冻结期排除，12 个暂归历史复权/数据资格
差异；另有 6 个 best 相同但分数值超容差。该诊断不改变信号规则、不生成订单。

## 研究湖交叉核对（2026-09-08 14:24）

25 个差异案例与 `C:\BigQMT\research\quant_data_lake\silver\bars_pit` 只读重算后，
21 个 QMT `front` 分数与研究湖原始收盘一致；12 个未解释 best 案例全部一致，说明下一步
重点是取得 PTrade 每标的 `dypre`/资格样本。4 个分数案例（`159667.SZ` 三日、
`159995.SZ` 一日）仍有 QMT 与研究湖来源差异。研究湖没有被切换为交易行情源。

当前已确认现有 PTrade 导出缺少逐标分数/资格字段，新增诊断合同见
`docs\12_v1_1_15_ptrade_per_security_diagnostic_contract_2026-09-08.md`。在取得一次不改变
策略逻辑的 PTrade 诊断运行结果前，不能继续宣称 parity 通过。

PTrade 源码审计无结构或语法发现；长日志审计确认 327 条 RC1 live signal、5,281 笔可归属成交、
无新增风险发现，但也确认日志没有逐标 score/eligibility 矩阵。因此当前阻塞是证据粒度缺失，
不是已发现的 v1.1.15 源码缺陷。

## Redis 短暂中断与恢复（2026-09-08 15:37）

一次只读复核时 Redis `127.0.0.1:6379` 短暂拒绝连接；项目 Redis 随后从
`appendonly-simulation.aof.11.base.rdb` 与增量 AOF 恢复并重新接受连接。恢复后的 QMT ping、
委托和成交查询通过，`allow_order_methods=false`、`orders=[]`、`trades=[]`，未调用任何订单/撤单方法。
证据：`runtime_data\evidence\simulation\redis_recovery_after_parity_probe_20260908_1537.json`。

## 模拟盘下单验证授权记录（2026-09-08）

用户确认账户 `90000001` 是模拟账户，并允许在门槛通过后进行适度下单验证。该授权只作用于
模拟盘；当前仍保持 `orders_enabled=false`。首笔订单必须经过 parity、Dry-run、账户快照和
下单前风控门禁，正式账户继续只读。

## 判断修正（2026-09-08 后续运行证据）

`KITLING_QMT_API` 证明同类令牌式 QMT 策略文件在出现
`CFromulaExpandData::loadFile parse error` 后，仍可实际进入 `PythonFormula construct`
并启动其 HTTP 输出服务。因此，令牌文件和这条解析日志都不是充分的失败判据。
`PY简单示例_1` 已按分钟线启动并取得历史 K 线，但样例没有可观察日志；其回调状态
尚不能仅凭“无输出”下结论。后续以 PythonFormula/业务日志、Redis 心跳和只读账户
查询作为验收证据；正式盘仍为只读，且验证前不允许下单。

## 本轮单策略验证（2026-09-08）

已停止 `PY简单示例_1` 与 `KITLING_QMT_API` 后，只运行
`BIGQMT_REDIS_DRYRUN`。BigQMT 仍仅完成行情订阅，未出现 `PythonFormula construct`、
Bridge 输出、Redis 键或 Redis 客户端连接；因此并发运行并非根因，阻塞仍在新策略的
QMT 加载/编译阶段。

已依据成功的 `KITLING_QMT_API.py` 准备仅使用标准 `logging` 的
`staging\\qmt_bridge_simulation\\QMT_LOGGING_PROBE.py`。它不含交易、账户和
Redis 操作，用于先验证 QMT 新建策略能否产生 `FormulaOutput` 日志。

## Bridge 启动证据（2026-09-08 09:12）

`BIGQMT_REDIS_DRYRUN` 已出现 `PythonFormula construct`，随后输出
`[bigqmt_signal_trader] init ok` 和完整启动诊断：QMT 注入的行情、交易函数已绑定，
`get_full_tick=OK`，且调整调度持续运行。说明模拟 BigQMT Bridge 的 Python 入口、
本地包加载、QMT 行情访问与生命周期回调均已跑通。

当前未启动 Redis RPC 的直接原因已定位：模拟 QMT `python` 目录缺少
`bigqmt_signal_trader_local_config.py`。Bridge 因而无法读取模拟账户标识和 Redis 配置，
主动输出 `rpc_service=NOT STARTED`；没有 RPC 服务、Redis 业务键或外部订单入口。
下一步仅需从项目 staging 的 example 生成模拟专用配置，明确保持 `mode=dryrun`，
然后验证 Redis 心跳与只读 RPC。正式盘不部署此配置、不启动 Bridge、不允许下单。

## 模拟 RPC 配置已部署（2026-09-08）

已仅在模拟 QMT 的 `python` 目录创建 `bigqmt_signal_trader_local_config.py`：连接
本机 Redis 第 5 库，账户类型为 STOCK，并将 `rpc_allow_order_methods` 固定为 `False`。
下载任务、全行情缓存、成交事件推送均关闭。配置需在当前 BigQMT 策略停止并重新启动后
生效；下一步验收 Redis RPC 的 ping 与账户、持仓的只读查询。正式版未作任何改动。

## P02 只读 RPC 验收通过（2026-09-08 09:27）

重启 `BIGQMT_REDIS_DRYRUN` 后，日志确认本地配置已加载，Redis RPC 已启动，且
`allow_order_methods=False`。通过项目 Redis 第 5 库对模拟 QMT 实测成功：

- `ping`：返回 Bridge 版本 `0.3.26`、STOCK 账户类型和订单方法关闭状态。
- `query_stock_asset`：返回模拟账户资产快照。
- `query_stock_positions`：返回 5 个 ETF 持仓。
- `query_stock_orders`、`query_stock_trades`：均正常返回空列表；本轮没有发出订单。
- `get_full_tick(511010.SH)`：返回完整五档 ETF 快照。

P02 的 QMT Python 入口、行情、账户/持仓/委托/成交只读 RPC、Redis 通道均已打通。
下一阶段是将这些只读数据标准化写入本项目的数据层与策略子账户账本；订单接口继续
保持关闭，正式盘继续不部署。

## P05 运行状态库首版通过（2026-09-08 09:52）

已实现主机侧只读 QMT Redis 客户端、SQLite WAL 运行状态库与 JSONL 追加审计。客户端
仅白名单允许 ping、资产、持仓、委托、成交和完整行情快照，代码中没有订单或撤单调用。
真实模拟盘采集已成功写入 `runtime_data\\state\\simulation\\qmt_runtime.sqlite3`：一轮
快照包含资产、5 个 ETF 持仓、5 个完整行情快照及空的委托/成交集合。单元测试通过。

当前继续推进 P04/P05：验证持续行情新鲜度、断连恢复与 QMT/SQLite 对账。多策略账本、
v1.1.15 信号和模拟下单均尚未开始；订单开关保持关闭，正式盘未部署。

## Redis 恢复与行情恢复通过（2026-09-08 10:30）

已对项目专用模拟 Redis 执行受控重启；其 AOF 恢复后，运行中的模拟 BigQMT Bridge 自动恢复
只读 RPC。随后 `ping`、完整行情、三轮主机采集和 QMT 权威事实对账均通过，持仓数量无差异、
委托/成交均为 0。此前陈旧的 `513100.SH` 同时恢复为新鲜、有成交和五档盘口的行情；五次诊断
采样的五个 ETF 均通过 180 秒新鲜度门禁。P05 的重启恢复证据已完成，P04 仍需更长时段稳定性
采样，订单继续关闭，正式盘未部署。

## P06 Dry-run 候选设计已冻结（2026-09-08）

在 P04 长时采样进行期间，仅完成了下一阶段的本地 Dry-run 合同与门禁设计，见
`docs\\11_p06_simulation_dry_run_design_2026-09-08.md`。它明确要求模拟环境、订单开关关闭、
新鲜 QMT 行情、策略袖套与请求幂等；未部署任何下单代码，未向 QMT 或 Redis 订单队列发送命令。
P06 仍为 `NOT_STARTED`，不得因该文档进入真实模拟下单。

## P04 行情稳定性通过（2026-09-08 11:20）

修正后的 30 分钟采样完成 61 次观测，5 个 ETF 均保持新鲜，未发生 RPC 超时或被行情门禁阻断的
标的。P04 标记为 `PASSED`，证据为
`runtime_data\\evidence\\simulation\\qmt_quote_health_30m_retry_2026-09-08_1050.json`。下一门禁是
P05 的本地订单意图幂等账本；它只处理本地 SQLite/JSONL 的 Dry-run 记录，不会调用 QMT 下单。

## P05 运行状态通过，进入 P06 Dry-run（2026-09-08 11:38）

P05 的 SQLite WAL、JSONL 审计、QMT/Redis 重启恢复及本地拟订单幂等测试均已通过，标记为
`PASSED`。P06 现为 `IN_PROGRESS`，但仅限本地 Dry-run：相同 `request_id` 重放返回
`DUPLICATE`，冲突和错误订单开关会失败关闭。没有调用 QMT 下单/撤单，模拟与正式账户均未改变。
下一步是将冻结的 v1.1.15 目标仓位输出接入该本地校验器，继续不下单。

## v1.1.15 PTrade 复现基线已冻结（2026-09-08）

已确认 v1.1.15 是 PTrade 分钟策略而非本项目原生策略。BigQMT 将以 PTrade 原始源码的 SHA-256
`2E7C…11E4` 与已对账长期回测导出作为金标准，逐项复现信号、时序、RC1/RC2、独立资金与状态机；
绝不把它简化为通用目标仓位。QMT 复现基线见
`strategy_baselines\\s10_d1_v1_1_15_ptrade.json`。当前首先验证 QMT 的日线复权/未复权完成K线
口径；在口径匹配前不生成可执行拟订单。

## P04/P05 连续性与恢复演练（2026-09-08 10:05）

已完成三轮有界连续采集、Redis 主机心跳和主机侧恢复对账。恢复时重新读取 QMT
券商事实并与 SQLite 上一快照比较，5 个持仓数量一致，委托/成交仍为空；该恢复演练
通过。行情则发现逐标的数据质量差异：4 个 ETF 快照新鲜，`513100.SH` 已陈旧约 50 分钟。
项目已将其标为 `BLOCKED`，并通过逐标的行情门禁排除在后续策略/数据湖使用之外；不会
静默改用第三方价格。P04 尚未通过，需先诊断陈旧行情与完成断连恢复测试。
## 托盘 SetTimer 修复与双版本重建（2026-09-14）

用户截图中的错误来自旧版托盘 EXE：`win32gui.SetTimer` 在当前 pywin32 中不存在。已将定时器调用改为 `ctypes.windll.user32.SetTimer/KillTimer`，并完成源码编译及 8 项 Coordinator/Host Agent 回归测试（8 passed）。模拟盘与正式只读托盘均已使用修复后的源码重新构建并替换根目录 EXE。旧文件保存在 `deploy/backups/20260914_before_settimer_fix/`。模拟盘启动后已向 Coordinator 成功发送 `HEALTHY_READONLY` 心跳；本次未执行任何交易。
## 原生托盘完整菜单恢复（2026-09-14）

已确认此前 PyInstaller 单账户 EXE 只实现了最小菜单，不能替代原生 C# 托盘。两套根目录 EXE 已恢复为功能完整的 C# 版本：QMT/MiniQMT/Redis/Bridge 状态与服务管理、看板、日志、诊断、Windows 启动项、策略开关、订单锁定提醒均在菜单中保留。EXE 重新以账户专属图标资源构建，运行时也直接提取 EXE 内嵌图标（模拟盘天蓝 `S`、正式版深蓝 `P`）。替换前的 PyInstaller 文件保存在 `deploy\\backups\\20260914_before_full_menu_restore\\`；本次只停止并替换托盘进程，没有停止 QMT/Redis、没有发送订单。
## 双托盘只读 Coordinator 心跳准备完成（2026-09-14）

当前完整 C# 托盘的本地验收：模拟与正式只读托盘均为“在线”，Redis/看板正常，两个账户的自动只读 Bridge Ping 通过，订单锁保持开启。已实现下一版心跳：每个账户托盘每 30 秒向 Coordinator 发送脱敏服务状态；Coordinator 端改为按账户保存同一主机的多个托盘快照，不再让后启动账户覆盖另一账户。Python 心跳脚本实测两账户均获 `202 accepted`，相关 3 项测试通过。该变更已在本机源码/构建校验完成，尚未替换正在运行的完整托盘 EXE，也尚未部署到 `.121` Coordinator；因此当前线上 Coordinator 仍是旧版单快照行为。
## Coordinator 双账户心跳已上线验收（2026-09-14）

两套完整原生托盘已重新构建、启动并在本机验证。`.121` 的 Coordinator 服务已先备份旧 `serve.py` 至 `/opt/bigqmt-coordinator/backups/20260914_before_profile_heartbeat/`，再更新和重启，systemd 状态为 `active`。验收接口 `/api/v1/hosts` 同时返回主机 `192.0.2.105` 的两个账户：`90000001`、`90000002`；其各自 QMT、MiniQMT、Redis、Bridge、Dashboard、Tray 均为 `UP`。所有心跳是 `HEALTHY_READONLY`，不携带凭据或订单，正式账户仍只读。
## Coordinator 只读监控看板已部署（2026-09-14）

Coordinator 首页 `http://192.0.2.121:18443/` 已部署为白底只读监控页。它以 10 秒刷新显示在线主机、账户数、未分配的 ACTIVE_EXECUTOR，以及每个账户的 QMT/MiniQMT/Redis/Bridge/Dashboard/Tray 状态；页面没有切换、下单或凭据能力。`.121` 部署前版本已备份至 `/opt/bigqmt-coordinator/backups/20260914_before_readonly_dashboard/`。HTTP 200 和 API 回灌均已验证，`192.0.2.105` 的 `90000001`、`90000002` 同时显示为六项服务 `UP`。
## ACTIVE_EXECUTOR 只读候选预览已上线（2026-09-14）

Coordinator 新增 `/api/v1/executor-preview`，首页据此显示执行候选数量，但不提供任何写入操作。候选条件为心跳不超过 90 秒，且 QMT、Redis、Bridge、Tray 均为 `UP`。验收结果：模拟账户 `90000001` 的 `192.0.2.105` 为合格候选；正式账户 `90000002` 虽健康但因 `PRODUCTION_READ_ONLY` 策略恒为不可执行。接口固定返回 `UNASSIGNED_READONLY` 与 `PREVIEW_ONLY_NO_LEASE_WRITE`，没有租约写入、主机切换或订单能力。`.121` 已备份前版至 `/opt/bigqmt-coordinator/backups/20260914_before_executor_preview/` 后部署，服务为 `active`；10 项回归测试通过。
## 托盘 Coordinator 状态闭环（2026-09-14）

两套完整托盘已重建并重启，保留原有全部菜单，新增只读 `Coordinator` 状态行。模拟账户本机显示“模拟执行候选（未分配，订单锁定）”；正式账户显示“只读／不可执行”。该状态由 `check_coordinator_lease_preview.py` 读取 `.121` 的只读预览，不申请、不续期、不释放租约。根目录 EXE 的前一版备份在 `deploy\\backups\\20260914_before_coordinator_menu\\`。托盘重启验收中，两个 Bridge Ping 均通过、心跳获 Coordinator 接收、订单仍锁定；20 项测试通过。
## Coordinator 迁移配置与全量回归（2026-09-14）

`config/machine.local.json` 现包含非敏感的 `coordinator.endpoint` 与 `coordinator.host_id`；Host Agent 心跳和托盘 Coordinator 预览均从该唯一机器覆盖文件解析，环境变量仅作为临时覆盖。因此迁移至 `.125` 或 `.113` 时只需修改这一处本机文件。两托盘已重建重启并再次验收：QMT/MiniQMT/Redis/Bridge/Dashboard/Tray 均 `UP`，两账户心跳均已回灌，订单继续锁定。22 项针对性测试及完整项目 `tests/` 回归 `145 passed` 均通过；PyInstaller 目录的第三方测试被明确排除，不影响项目测试结论。
## Coordinator 双节点主备后备方案（2026-09-14）

记录为未来可选架构，当前不实施：两台 Ubuntu Coordinator 运行主备复制，OpenWrt 仅作为轻量见证节点参与多数派 Leader 选举。任一 Ubuntu 故障后，另一台须与 OpenWrt 形成多数派才可接管，并递增 `coordinator_epoch`；孤立旧主的 fencing token 因此失效。OpenWrt 不运行 QMT、不保存券商凭据、不下单、不保存交易账本；OpenClaw 保持业务 Agent 身份，不参与 Leader 选举。NAS 仍只作为发布、备份与审计副本，不能作为仲裁或实时锁。若 OpenWrt 持久存储/稳定性不足，则以极小 Ubuntu VM 替代见证节点。
## OpenClaw 只读 MCP/Skill 候选包（2026-09-14）

已构建不可覆盖的本机候选包 `dist\\openclaw-bigqmt-bundle-0.1.0-readonly\\`。其中包含 `bigqmt-operator` Skill、stdio JSON-RPC MCP 适配器、MCP 注册模板、项目覆盖文件、manifest 与 SHA256。实际协议探测仅返回 `bigqmt_get_fleet_status`、`bigqmt_get_executor_preview`、`bigqmt_get_project_progress` 三个工具；不存在确认、取消、租约写入、Redis、QMT RPC、Shell 或订单工具。25 项测试通过。该包未写入 NAS、未安装到 `.125/.113`、未发放 token，等待 AP4 后再进行目标机本地复制、校验、MCP probe 与 Skill check。
## OpenClaw 只读候选包已发布 NAS（2026-09-14）

候选发布物已安全复制至 `\\192.0.2.236\\truenas\\kitling_QMT\\kitling_bigqmt\\releases\\openclaw\\candidate\\openclaw-bigqmt-bundle-0.1.0-readonly\\`，并写入 channel 指针 `channels\\openclaw.json`。先 staging 复制、核对 manifest SHA-256 后才改名发布；包内 6/6 文件 checksum 均匹配。`.125` 与 `.113` 使用同一个不可变 release `0.1.0-readonly`，但分别在本机安装、分别设置 `machine.local.json`、分别绑定 OpenClaw Agent 身份与未来 token；绝不共用运行目录或凭据。该 release 仍为 observer-only，尚未安装到任一目标机。
## OpenClaw `.125` / `.113` 安装说明已发布 NAS（2026-09-14）

面向 `.125` 主 Agent `kitling`（WSL/Linux）和 `.113` 主 Agent `chief`（Windows）的安装任务说明已发布到 `\\192.0.2.236\\truenas\\kitling_QMT\\kitling_bigqmt\\instructions\\128_openclaw_readonly_install_125_113_2026-09-14.md`，并已校验本地/NAS SHA-256 一致。该文件规定两机共用同一 immutable observer-only release、分别本地安装与配置 Host ID、执行 checksum/Skill/MCP probe、再分别写报告。没有部署任何执行功能。
## OpenClaw 独立 Python 3.11+ observer 包替代发布（2026-09-14）

目标 Agent 报告显示 `.113` 没有 Python 3.12 且没有本地 BigQMT 项目，原 `0.1.0-readonly` 的目标机依赖不合适。已发布自包含 `openclaw-bigqmt-bundle-0.1.1-readonly`，NAS channel 已原子更新且旧 channel 备份为 `channels\\history\\openclaw_20260914_before_0.1.1.json`。新版仅需 Python 3.11+、本地非敏感 endpoint JSON，不需要 QMT/Redis/BigQMT checkout；stdio 实测可返回三个只读工具和 fleet 数据。新安装说明为 `instructions\\129_openclaw_standalone_observer_install_125_113_2026-09-14.md`，NAS copy hash 已验证。旧 `0.1.0` 保留但已标记为不应安装。

## OpenClaw v0.1.1 完整性拒绝与 v0.1.2 重发（2026-09-14）

`.125` 的 0.1.1 实际 stdio 探测和三个只读查询均通过，但 `README_INSTALL.md` 在 Windows/Linux 复制路径中出现 3 字节 CRLF/LF 漂移，故 5/6 checksum 通过不构成发布验收，0.1.1 明确拒绝为活动 MCP。已发布 `openclaw-bigqmt-bundle-0.1.2-readonly`：README 改为固定 UTF-8/LF 字节写入，发布源 6/6 payload hash 及 manifest/channel SHA-256 均通过。channel manifest SHA-256 为 `D2A2230997B909A9B3C7BA919DFF69EF27219FBB7887781A14CD3ED9A18BAB67`。新安装规约为 `instructions\\130_openclaw_standalone_observer_install_125_113_v0_1_2_2026-09-14.md`；两机均须先本地复制、6/6 校验并只作 stdio 验收，仍不得注册任何执行、租约或下单功能。

## 托盘状态行接入桥接快照新鲜度（2026-09-16）

托盘状态行现在直接带桥接快照年龄，不再依赖事后体检才发现快照过期。`src/kitling_bigqmt/tray_health.py` 新增 `snapshot_freshness(config)` 作为唯一测量路径，返回 status/detail/latest_run_id/observed_at/age_seconds/max_age_seconds/fresh，原 `_bridge_snapshot_health()` 改为调用它，体检脚本与托盘口径统一；`src/kitling_bigqmt/bridge_probe.py` 新增 `reply_evidence()`（从 `reply["data"]` 取 version/rpc_revision 并保留顶层回退），`probe_bridge_ping()` 记录原始 `bridge_reply`；`tray/BigQMTAccountTray.cs` 新增 `SnapshotFreshness()`（60 秒缓存）并把「快照 X 分钟前（上限 75 分钟）」拼进状态行。快照过期只体现在文字上，不改变托盘图标颜色（按用户要求避免误报）。实测两个档案的 `runtime_data/audit/<profile>/native_tray.jsonl` 最新 status_refreshed 均带该字段，模拟 13 分钟、上限 4500 秒。新增 `scripts/check_snapshot_freshness.py` 与 `tests/test_tray_health.py` 四个用例，`orders_enabled=false`。

## Dashboard 侧边栏跳转与页面补齐（2026-09-16）

`scripts/run_local_dashboard.py` 六个侧边栏项全部带 `data-route`，`wireSidebar()` 按 `node.dataset.route`（带兜底路由表）解析；「策略袖套」改名「策略账户」并与 `bigqmtRouteTitles.strategies` 对齐；策略页用 `renderLightBeforeStrategyAccounts()` 把基础视图存入 `window.__bigqmtStrategyExtra`，再以 `queueMicrotask` 包装 `renderLight` 追加「v1.1.15 收盘影子信号」与「策略池登记」；总览分支现在会复位标题、导航高亮与 `document.title`。同时修掉一个真实缺陷：Windows `ThreadingHTTPServer` 默认 `allow_reuse_address`，旧 dashboard 进程未退出时会与新进程同时绑定同一端口，浏览器拿到旧内存页面（磁盘新、HTTP 旧）。现在每台响应带 `X-BigQMT-Dashboard-Build`（mtime+size 十六进制），端口已被占用则拒绝启动并返回 3。实测 17890/17891 均返回 `6aa9da47-9ca0`，`scripts/verify_dashboard_sidebar.js`（Playwright）两档案路由 6/6 全通，模拟策略登记 2 条、正式 0 条（正式无策略登记区块属预期），报告落 `runtime_data/artifacts/dashboard_sidebar/verify_report.json`。

## Bridge 每日运行证据留档（2026-09-16）

新增 `scripts/record_bridge_daily_evidence.py`：一次只读 ping，加本地快照年龄与订单锁状态，输出 6 项检查（bridge_ping / bridge_version_reported / bridge_revision_reported / account_match / snapshot_fresh / order_lock），写入 `runtime_data/evidence/<profile>/bridge_daily/bridge_daily_<YYYYMMDD>.json`，同日重复执行按合并处理（上限 96 条）。托盘 `tray/BigQMTAccountTray.cs` 在 16:30 后为两个档案触发 `BridgeDailyRecordIfDue`（置于 simulation-only 闸门之前），失败每 10 分钟重试，结果写审计 `bridge_daily_evidence`。首个留档实测两档案均 `status=PASSED`、`bridge_version=0.3.26`、`rpc_revision=20260715-execution-snapshot-v1`、6/6 通过；模拟 `allow_order_methods=true`、正式 `false`。新增 `tests/test_bridge_daily_evidence.py` 七个用例，全量回归 224 passed。

## 托盘审计日志换行截断缺陷修复（2026-09-16）

托盘 `Audit()` 原本手工拼 JSON，只转义反斜杠和双引号，未处理控制字符。当 `detail` 里放进多行工具输出（`qmt_auto_start_login`、`qmt_start_requested` 以及各 `*_blocked` 分支）时，原始换行把一条记录劈成多个物理行，任何按行解析 JSONL 的读者都会静默跳过。修复前实测：模拟 `runtime_data/audit/simulation/native_tray.jsonl` 9494 条中 762 条无法解析，正式 `runtime_data/audit/production_readonly/native_tray.jsonl` 9088 条中 697 条无法解析；影响面仅限审计可读性，托盘体检、桥接快照与下单链路均不受影响。

修复为 `tray/BigQMTAccountTray.cs` 新增 `JsonEscaped(string)`（第 825 行），覆盖双引号、反斜杠、换行、回车、制表符以及所有小于 32 的码点（`\uXXXX`），`Audit()`（第 819 行）的 event 与 detail 均改走该函数，确立「一条记录恒定占一个物理行」的不变量。`scripts/build_native_account_trays.ps1` 于 09:27:30 重新编译，模拟 EXE SHA-256 `25B97F62D692515981572E0F1D8885E1A8F5B0D9E84E24739B4A070FE3C70B26`、正式 EXE `5DC4A81AC103109C7B696D5B0390E1DE6E012006545034775D5F0476EA474D13`，与 `tray/BigQMT_native_tray_checksums.sha256` 完全一致；两个托盘于 09:28:40 / 09:28:41 重启（PID 12768 / 11680），运行中的即为验收构建。

验证方式：统计以 `{"event_time"` 开头且 `json.loads` 失败的物理行，并与重新编译时间点比对。最后一处无法解析的行是模拟第 9441 行、正式第 9031 行，均在重新编译之前；重新编译之后写入的记录全部可解析（模拟 15/15、正式 13/13，失败 0）。历史坏行按要求不做回溯改写，因此新增只读核查工具 `src/kitling_bigqmt/audit_log_integrity.py` 与 `scripts/check_audit_log_integrity.py`：`--max-bad` 表达已知历史基线，缺省 0 表示新增损坏即判失败。新增 `tests/test_audit_log_integrity.py` 五个用例，全量回归 229 passed（原基线 224 + 新增 5）。`orders_enabled=false`。

## 2026-09-16 16:55 · 换仓拆腿调度修复 + 模拟盘预演就绪


托盘 `SimulationCycleIfDue` 旧版在 `SUBMITTED` 后立即把今天标记为已完成，等价于卖出腿之后的买入腿再也不会被触发，整次换仓会停留在现金。改为：`SUBMITTED` 且 `side=SELL` 时不封盘、`nextExecutionAttempt` 推迟 60 秒后会再调用 runner；每场会话设 `MaxSimulationCycleAttemptsPerSession = 30` 上限；`BLOCKED_DUPLICATE_OR_UNRECONCILED_ATTEMPT` / admission / reconciliation 全部改为可重试 2 分钟；A 股交易窗口之外的 fail-closed 块仍立即封盘。重新编译落盘 SHA-256：模拟 `6F6AC38E7DAEF9BAF5B529D7627F69C149793122A50A4CF28ED8E2C0226D3BEC`、正式 `CA5268A7D46D5A8EFAB7B8B723904279D7615BE7794C4D73068C72A0EB97D92B`。两个托盘 16:45 重启（PID 1948 / 26104），`http://127.0.0.1:17890` 与 `http://127.0.0.1:17891` 返回 200，`check_tray_health` 双侧 HEALTHY。

## 2026-09-16 16:55 · 真实入场日和首次换仓窗口


袖套填充日期 `1789093235` 对应 2026-09-11 10:20:35 +08:00，因此持有期守卫按真实入场起算：`signal_day=20260916` 仅得 4/5 → 当日 "a completed-close signal executes on a later trading day"；`signal_day=20260917` 满 5/5 且 `<` trade_day 20260918，故 **最早的真实换仓窗口为 2026-09-18（周五） 09:35**。 9 月 17 日托盘会自动以 `ALIGNED_NO_ORDER` 收口，不会误下单。

## 2026-09-16 16:55 · 换仓空跑预演


新增 `src/kitling_bigqmt/switch_rehearsal.py` 与 `scripts/rehearse_v1_15_switch.py`（纯函数 + 只读 RPC），针对 09-18 场景产出两条 plan：SELL `160723.SZ 41400 @limit 2.349`，BUY `162411.SZ 94500 @limit 1.034`，两个 signal_id 不冲突；证据留档在 `runtime_data/evidence/simulation/switch_rehearsals/rehearsal_20260918_legs.json`。新增 `tests/test_switch_rehearsal.py` 6 用例，全量 235 passed in 18.44s。

## 2026-09-16 16:55 · 阻塞收口


`progress/blockers.json` 三条 ACTIVE `TRAY_INTERACTIVE_DESKTOP_LAUNCH`、`SIMULATION_BRIDGE_POST_RESTART_LOGIN_AND_AUTORUN`、`PRODUCTION_BRIDGE_REDIS_DB_ALIGNMENT_RELOAD` 改为 RESOLVED，附 16:40~16:41 启动日志、bridge_auto_probe=PASS、Redis PONG、coordinator 心跳为证据。`orders_enabled=false`。

## 2026-09-16 19:09 · Coordinator 影子容器 C0/C1 本地实现

已开始 Coordinator 容器化的本地开发，未部署、未连接 `.121`、未修改当前权威 `192.0.2.121:18443` systemd 服务。新增 `coordinator_instance.py`：状态目录进程锁、稳定 UUID instance ID、持久 `epoch_floor` 与实例/epoch 信封校验；旧备份恢复后 epoch 只能单调上升。新增 `coordinator_key_authority.py`：Coordinator 仅接收本机授权 Key 的 SHA-256 指纹观察而不接收 Key 明文；同一账户发现两个不同 Windows 主机持有有效 Key 时产出 `DUPLICATE_KEY_LOCKDOWN`，所有候选均不可执行，待其中一台删除/失效 Key 后才重新评估。当前结果依然 `orders_enabled=false`，正式账户未获得任何执行能力。

新增六份 C0 合同 schema（Key、Key observation、订单事件、成交、策略运行状态、策略净值、迁移 checkpoint）和 shadow OCI 产物：`container/coordinator/Dockerfile`、只读 `compose.shadow.yaml`、入口写入硬关闭检查、容器本地 healthcheck、不可运行的未来 production 模板。影子固定为 `.121:18666`、非 root、只读根文件系统、独立状态卷 `/var/lib/kitling-bigqmt-coordinator-shadow`；不会共享 `18443` 的数据库/WAL/锁/instance ID。测试收集范围也收敛到项目 `tests/`，避免 PyInstaller 临时目录的第三方测试冲突。定向 29 项与全量 244 项测试均通过；详见 `docs/140_coordinator_shadow_container_c0_c1_implementation_2026-09-16.md`。

## 2026-09-16 19:14 · Coordinator SQLite 在线备份与 Shadow 副本准备

新增 `src/kitling_bigqmt/coordinator_backup.py` 和三个只面向本地数据库文件的 CLI：`backup.py`、`verify_database.py`、`prepare_shadow_database.py`。它们使用 SQLite `backup()` API，而不是复制运行中的 `.sqlite3`/`-wal`/`-shm` 文件；备份后执行 `integrity_check`、生成 SHA-256，并在影子副本内将继承的所有 lease 置为过期。源数据库不被修改。修复了 Windows 备份落盘时可能残留 SQLite 句柄造成 `WinError 32` 的问题，现显式关闭目标连接后再替换副本。在线备份专项 3 项和 Coordinator 相关 21 项均通过；全量回归 `247 passed`。本机没有 Docker，故 OCI 镜像尚未构建，也没有向 `.121` 上传或启动容器。

## 2026-09-16 19:22 · C2 本地 Outbox 与 Coordinator 事实去重基础

新增 `coordinator_outbox.py` 与 `coordinator_event_store.py`，为后续主机迁移、策略延续、收益统计和 NAS 归档建立可重放事实链。Host Agent 本地 SQLite WAL Outbox 只允许订单事件、成交、策略运行状态、策略 NAV、checkpoint 五类记录；按 `event_id + canonical SHA-256` 保证幂等，网络失败只积压重试，收到确认才 ACK；密码、凭据、授权 Key、secret/access token 等字段硬拒绝。Coordinator 侧事实库对同 ID 同内容去重、对篡改重放拒绝整批。当前 Coordinator 未开放任何 ingest、订单或 Lease 写路由；`/api/v1/facts/ingest`、`/api/v1/orders`、`/api/v1/leases` 仍为 404，避免在 Host Agent 身份签名、时间窗与重放保护完成前暴露内网写入口。专项 14 项、全量 `252 passed`；详见 `docs/141_coordinator_outbox_fact_store_c2_foundation_2026-09-16.md`。

## 2026-09-16 19:30 · Host Agent 认证事实接收（默认关闭）

新增 HMAC-SHA256 Host Agent 身份 envelope、60 秒有效时间窗、主机/key-id 绑定、canonical body hash 和 request replay 表；身份材料与账户执行授权 Key 分离。`scripts/coordinator/serve.py` 新增可选 `POST /api/v1/facts/ingest`，仅当 `BIGQMT_FACT_INGEST_ENABLED=1` 且受信任主机 secret 通过 Secret 机制提供时启用，否则保持 404。启用后的响应固定 `facts_only=true`、`orders_enabled=false`，只归档订单事件、成交、策略运行、NAV、checkpoint，拒绝订单、Lease、确认和任何 QMT/Redis 调用。`.121:18443` 尚未加载此路由，影子容器也未部署。认证事实路由、重放、篡改和旧写路由边界通过；全量 `256 passed`。详见 `docs/142_authenticated_fact_ingest_opt_in_2026-09-16.md`。

## 2026-09-16 19:42 · Host Agent 事实身份分发与轮换

新增 `host_fact_identity.py` 与 `manage_fact_identity.py`：事实传输 Secret 与账户执行授权 Key 分离，Secret 文件只能放受保护的服务/容器 Secret 目录；支持同一主机新旧 key 并行轮换、撤销旧 key、未知/重复 key 拒绝，脚本不打印 secret 且禁止写入项目树。Coordinator 读取路径改为 `BIGQMT_FACT_TRUSTED_HOSTS_FILE`，默认事实接收仍关闭。轮换不改变账户双 Key 冲突锁定和任何订单门禁。Secret 生命周期、Windows ACL 和 `.121:18666` 影子启用前检查写入 `docs/143_host_fact_identity_distribution_rotation_2026-09-16.md`。新增测试后全量 `259 passed`，未生成真实项目密钥、未启用 `.121` 路由。

## 2026-09-16 20:00 · `.121` Shadow 容器运行时预检

SSH 只读预检确认：`.121` 可达，现有 `kitling-bigqmt-coordinator.service` 为 `active`，根/var 磁盘约 105 GB 可用；Docker、Podman、nerdctl、Buildah、containerd 均未安装或未运行。故暂不能构建或启动 `.121:18666` Shadow；本地镜像与 Compose 产物、`18443` 权威服务、Windows 托盘均不受影响。安装 Docker Engine + Compose plugin（或指定 Podman）需要 Ubuntu 软件包和 sudo 变更，本轮未执行，详见 `docs/144_coordinator_shadow_121_runtime_preflight_2026-09-16.md`。待授权后再安装，随后严格按在线备份→影子启动→13 项门禁→24–48 小时 soak，不切换 `18443`。

## 2026-09-16 20:47 · `.121` Docker 运行时安装完成

按用户授权在 `.121` 安装 `docker.io` 与 `docker-compose-v2`。验证通过：Docker Engine `29.1.3`、Compose `2.40.3`、`systemctl is-active docker=active`、`sudo docker info` 正常（0 容器、0 镜像）。未加入 `docker` 用户组，未修改 `18443`，未启动 `18666` Shadow；详见 `docs/146_coordinator_docker_install_121_2026-09-16.md`。下一步为单独的最小构建上下文上传、SQLite 在线备份和 Shadow C3/C4 验证。

## 2026-09-16 21:00 · `.121:18666` Shadow C3/C4 部署

已在 `.121` 构建 `kitling-bigqmt-coordinator:shadow-20260916`（镜像 ID `709d7cd46b83…`），使用可配置的 DaoCloud Python 3.12 基础镜像；通过 SQLite `backup()` 生成并校验独立 Shadow 数据库。`kitling-bigqmt-coordinator-shadow` 已以非 root、只读根文件系统运行并健康，监听 `18666`。`/readyz`、三只读查询均 200；facts ingest、orders、leases 均 404。`18443` systemd 权威服务仍 active 且心跳不变。详见 `docs/147_coordinator_shadow_121_c3_c4_deployment_2026-09-16.md`。

随后完成一次 Shadow 受控重启演练：容器约 15 秒内恢复 `running|healthy`，`RestartCount=0`，`18443` 全程 `active`。当前进入 24–48 小时 soak 阶段。

## 2026-09-16 22:32 · Coordinator Dashboard 空白页面修复

定位并修复内嵌 Dashboard JavaScript `render()` 少一个右括号导致的浏览器语法错误。Shadow 镜像已更新为 `shadow-20260916-fix` 并健康运行；权威端点先回滚整文件版本差异，再在远端旧版上做单字符热修复并保留备份。Playwright 实测 `18443` 显示 1 台主机/2 个账户、`18666` 显示预期空 Shadow 列表，两个页面均无 page error。详见 `docs/148_coordinator_dashboard_js_hotfix_2026-09-16.md`。

## 2026-09-17 06:10 · Shadow soak 定时巡检启用

新增 `scripts/coordinator/soak_probe.py`，在 `.121` 以 systemd timer 每 5 分钟检查权威 `18443`、Shadow `18666` 的 readyz 和 Shadow 只读进度，并写入 `/var/log/kitling-bigqmt-coordinator-shadow/soak.jsonl`。首次修复目录权限后验证 `ok=true`；不访问 Docker socket、数据库、QMT、Redis 或 NAS。全量回归 `262 passed in 18.37s`，详见 `docs/149_coordinator_shadow_soak_monitor_2026-09-17.md`。

## 2026-09-16 20:15 · Host Agent Outbox 签名投递编排

新增 `host_fact_uploader.py`，将本地 Outbox pending 批次与 Host Fact Secret 签名 envelope 接起，但不执行网络调用。只有 Coordinator 明确返回且属于原批次的 `accepted/duplicates` event ID 才会 ACK；空 ACK、未知 ID、拒绝、超时均保留 pending；`REPLAYED` 必须携带原始批次 ID。该层不接触 QMT、Redis、Lease 或订单。全量 `261 passed`，详见 `docs/145_host_fact_outbox_delivery_orchestration_2026-09-16.md`。`.121` 运行时未安装，事实上传尚未启用。

## 2026-09-17 12:10 · Shadow 事实接收与重放验证

按立即推进顺序，在 `.121:18666` Shadow 安装 `.105` 的事实签名 Secret（key-id 仅记录元数据，Secret 不进入项目树、NAS 或报告），并启用 facts-only 网络入口。容器以 `uid=10001` 读取 `0440 root:10001` Secret；Shadow `/readyz` 与权威 `18443` 均健康，权威 `/api/v1/facts/ingest` 仍为 404。使用合成 `STRATEGY_RUNTIME` 事件验证：合法 HMAC envelope 首次返回 `202 ACCEPTED`，原样重放返回 `202 REPLAYED`，空 envelope 返回 `400 FactAuthenticationError`；成功响应均为 `facts_only=true`、`orders_enabled=false`。这证明 Shadow 认证、时间窗、主机绑定与 request replay 保护可用，但尚不是 `.105` 真实 Outbox 在线接入证据；下一步为 Host Agent 本地 Outbox 只读生成与断网重试/ACK soak。详见 `docs/150_shadow_fact_ingest_105_synthetic_replay_2026-09-17.md`。

## 2026-09-17 12:15 · `.105` 本地 Outbox 到 Shadow 投递

新增 `scripts/host_agent/collect_runtime_fact.py`，从 `.105` 两个 profile 的 native tray 审计最新状态行生成本地 `STRATEGY_RUNTIME` 事实；事件采用稳定 UUID、SQLite WAL 和 `LocalOutbox` 幂等约束，脚本只读本地文件，不调用 QMT、Redis、Coordinator 或订单接口。模拟 `90000001` 与正式只读 `90000002` 各生成 1 条待投递事实，使用受保护 Host Fact Secret 签名后投递 `.121:18666`，两条均 `202 ACCEPTED`，按返回 event ID ACK 后两个 pending 均为 0；响应均 `facts_only=true`、`orders_enabled=false`。临时 envelope 已清理，权威 `18443` 仍未开放事实入口。详见 `docs/151_host105_outbox_shadow_delivery_2026-09-17.md`。

随后新增 `scripts/host_agent/deliver_fact_outbox.py`，将签名批次与 ACK 规则固化：默认拒绝非 `18666` Shadow 入口；网络失败、超时、HTTP 错误、空/异常 ACK 均保留 pending，只有 Coordinator 返回的本批 event ID 才能 ACK。命令在空 pending 时返回 `EMPTY` 且不产生网络写入；当前尚未接入托盘自动 tick。全量回归 `267 passed`。

已将 facts-only 采集/投递调用接入 `tray/BigQMTAccountTray.cs` 的低频维护调度（每 5 分钟，独立于 v1.1.15 下单调度），但因两个活动 EXE 正在占用，未覆盖正式托盘；新版本只编译到 `runtime_data/_build/host_fact_tray_compile_20260917/` 供验证。待用户退出两个托盘后再替换、重启并观察断网/恢复 soak。

补充验证：投递器在 Shadow 不可达时返回 `RETRY_PENDING`，attempts 增加且事件不被 ACK；`.121` 的 5 分钟 systemd Shadow soak timer 仍 active，最新三次样本均 `ok=true`，`18443/18666 readyz=200`、Shadow `shadow_readonly`。本轮全量回归 `268 passed`。

## 2026-09-17 13:58 · `.105` Native Tray facts-only Tick 正式部署

两个旧托盘退出后，重新编译并启动 `BigQMT_Simulation_90000001.exe`（PID 27644）与 `BigQMT_Production_ReadOnly_90000002.exe`（PID 23144）。新版本的每 5 分钟 facts-only tick 已在两个 profile 各成功投递一次，Shadow 返回 `202 ACCEPTED`、`pending=0`；Redis 与 Dashboard 被托盘自动补拉后恢复，两个托盘状态均回到「在线」。模拟与正式 Bridge 只读 ping 通过，正式账户 `allow_order_methods=false`；v1.1.15 当日 cycle 因真实成交持有期 guard（4/5）安全阻断，未产生 broker/order call。详见 `docs/152_native_tray_fact_tick_deployed_2026-09-17.md`。

## 2026-09-17 · `.125/.113` Host Agent 0.1.0 Shadow 候选包

已生成并发布不含 Secret 的 facts-only 候选包到 NAS：`releases/host_agent/candidate/0.1.0-shadow/`，含采集器、可重试投递器、Fact Secret 生成器、最小依赖模块、机器配置模板、安装说明和 SHA-256 清单。`.125` 与 `.113` 后续必须各自本机生成独立 Secret；本轮只发布候选包，尚未在两台主机安装，也未授予任何执行权限。详见 `docs/153_host_agent_candidate_010_shadow_publish_2026-09-17.md`。

已另外写入 `.125` VS Code + Claude 执行清单：`instructions/host_agent/125_vscode_host_agent_install_steps_20260917.md`。清单要求 Windows PowerShell 执行、独立生成 `.125` Secret、只投递 `18666` Shadow、生成无敏感信息安装报告；不在 WSL 中运行、不触碰 `18443`、不启用订单能力。详见 `docs/154_host_agent_125_vscode_execution_steps_2026-09-17.md`。

## 2026-09-17 15:05 · `.125/.113` Portable Host Tray 0.2.0 部署包

已生成 `BigQMT_Host_125` 与 `BigQMT_Host_113` 两套便携包：每套只有一个 facts-only 原生托盘 EXE、`machine.local.json`、本机 SQLite WAL Outbox、首次启动脚本与最小采集/签名投递依赖。配置使用相对目录，复制到目标机本地目录即可；首次运行才在本机 `secrets/` 生成并 ACL 保护 Host Fact Secret，发布包、NAS 与跨主机复制均不包含 Secret。Host Agent 只读取既有原生账户托盘审计日志；若日志尚未出现，托盘以红色等待状态启动，不创建虚假运行证据且不启动/控制 QMT。

`.125` 本地 staging 已发布到 `\\192.0.2.125\kitling_QMT_work\kitling_bigqmt\BigQMT_Host_125`；NAS 源已发布到 `\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\releases\portable_host\candidate\0.2.0`。三处 SHA-256 检查均通过，所有 release `secrets/` 目录为空；全量回归 `268 passed in 21.18s`。只允许 `.121:18666` Shadow facts endpoint，`orders_enabled=false`，权威 `.121:18443` 未触碰。详见 `docs/155_portable_host_bundle_020_release_2026-09-17.md`。

## 2026-09-17 15:25 · Portable Host Tray 0.2.1 Secret 路径修复

`.125` 的复核正确指出 0.2.0 配置把 Fact Secret 放在包内，而 `manage_fact_identity.py` 按设计拒绝写入自己的项目树。因此 0.2.0 标记为不可运行并保留作审计，不覆盖或删除。新的不可变 `0.2.1` 将两台主机的 Secret 路径改为本机 `C:\ProgramData\Kitling\BigQMT\host-facts\<key-id>.json`；包内仍保留 SQLite WAL Outbox、日志和非敏感代码，但不再有 `secrets/` 目录。

`.125` 新 staging 为 `\\192.0.2.125\kitling_QMT_work\kitling_bigqmt\BigQMT_Host_125_0.2.1`，交接文件为 `125_portable_host_021_handoff_20260917.md`；NAS 新源为 `releases/portable_host/candidate/0.2.1/`。三份目标的 checksum 及外部 Secret 路径均已验证。不得在 Git Bash/WSL 以 `ls/find` 判断 Windows UNC 发布路径；使用 Windows PowerShell。无 Coordinator trust enrollment、无订单、无 lease、无 `18443` 改动。详见 `docs/156_portable_host_bundle_021_secret_path_fix_2026-09-17.md`。
