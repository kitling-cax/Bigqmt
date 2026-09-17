# BigQMT 多主机、Coordinator 与 OpenClaw V2 实施确认稿

日期：2026-09-14  
状态：`PLANNED_PENDING_USER_CONFIRMATION / NO_RUNTIME_CHANGE`

## 1. 已确认的最终决定

| 项目 | 已确认方案 |
|---|---|
| 开发和当前主力 QMT | `192.0.2.105`；保持现有 F 盘 BigQMT、模拟 QMT、正式 QMT 目录 |
| 当前模拟执行权 | 开发期间仅由 105 作为 `ACTIVE_EXECUTOR` 候选；现有模拟订单门禁仍独立生效 |
| Coordinator | `192.0.2.121` Ubuntu 24.04；只协调、不直接调用 QMT 或下单 |
| 初期访问地址 | `https://192.0.2.121:18443/`；不要求 DNS、不开放公网、不做端口映射 |
| Coordinator TLS | 私有 CA，证书包含 IP SAN `192.0.2.121` |
| OpenClaw | 已部署在 `192.0.2.125` 与 `198.51.100.113`，均为多 Agent 模式 |
| OpenClaw 发布方式 | NAS 是 immutable release 源；每台 OpenClaw 从 NAS 校验后复制到本地并安装，不从 SMB 实时运行 |
| 下单 Agent | 双主机候选已确认：`execution@198.51.100.113` 与 `xiaocai@192.0.2.125`；AP5 时只能选择一个作为当前账户的唯一手机订单入口 |
| 正式账户 | `90000002` 继续 `READ_ONLY`，本方案不创建正式下单 Agent |
| 稳定后迁移 | 105 → 125 人工迁移执行权；113 为后续 `STANDBY_READONLY` |

## 2. 最终架构

```text
手机 / 受允许频道
       |
       v
OpenClaw 指定 Agent（125 或 113）
       |  本地 Skill + MCP client
       v
192.0.2.121:18443
  Agent Gateway / BigQMT MCP
       |
       v
  Coordinator
  节点、账户、租约、fencing、intent、审计
       |
       |  Windows 主机主动拉取意图
       v
192.0.2.105 当前主力 Windows Host Agent
  Tray / Execution Engine / Redis / BIGQMT_BRIDGE / QMT
       |
       v
模拟账户 90000001

192.0.2.125：未来迁移目标 / OpenClaw 多 Agent
198.51.100.113：未来备用只读节点 / OpenClaw 多 Agent
192.0.2.236：NAS 发布、报告、审计副本、备份；不是运行库
```

## 3. 不可突破的安全边界

1. 账户维度只有一台 `ACTIVE_EXECUTOR`；其余全部 `STANDBY_READONLY`。
2. OpenClaw 只能调用 Agent Gateway 的受类型约束 MCP 工具，不能直接连接 Redis、QMT RPC、SQLite 或
   Bridge 通用接口。
3. Coordinator 失联、租约过期、fencing token 不匹配、快照过期、账户不符、订单状态未知时，一律禁止
   新订单。
4. Coordinator 只能管理租约和订单意图，不能绕过 Windows 本机 Execution Engine。
5. Windows Host Agent 通过 HTTPS 主动拉取订单意图；不开放 Redis、QMT RPC 或 SQLite 给网络。
6. NAS 不能承载在线 lease、订单队列、活动 SQLite、Redis 或直接执行代码。
7. 只有券商真实成交可以更新策略现金、持仓、净值和收益。
8. 正式环境必须保留物理隔离配置和只读白名单；本计划没有正式交易放行步骤。
9. `execution@198.51.100.113` 与 `xiaocai@192.0.2.125` 是不同主机的候选执行 Agent；同一账户同一
   时间只允许其中一个具备 confirm scope，且必须与当前 `ACTIVE_EXECUTOR` 主机映射一致。

## 4. Coordinator 控制台功能

初期从 105 浏览器访问：

```text
https://192.0.2.121:18443/
```

| 页面 | 初期能力 | 后续能力 |
|---|---|---|
| Fleet Overview | 节点、QMT、Redis、Bridge、Tray、版本、心跳 | 异常汇总和告警 |
| Accounts | 账户、持仓、委托、成交、策略袖套、收益 | 主查询源切换预览 |
| Strategies | v1.1.15 版本、策略状态、净值、曲线 | PAUSED/SHADOW/SIMULATION_EXECUTION 控制 |
| Leases | 当前执行主机、token、到期、冲突 | 请求迁移、人工授予执行权 |
| Intents | preview、confirm、领取、结果、拒绝原因 | 手机订单链路审计 |
| Releases | 当前版本、候选版本、回滚点 | NAS 更新与回滚审计 |
| Tests/Progress | 阶段、测试、阻塞、证据 | 多主机专项百分比 |

主机切换不是直接按钮下单，而是：暂停新增订单 → 对账 → 撤销旧 lease → token 递增 → 目标主机只读验证 →
用户确认 → 授予新 lease。初期没有第二台 Host Agent 时，页面只展示 105，不提供迁移执行操作。

## 5. MCP 与 Skill 的交付结构

两者都交付：

- **BigQMT MCP Server**：运行于 121 Agent Gateway，提供真实、类型化、受 scope 限制的工具；
- **`bigqmt-operator` Skill**：安装在每个授权 OpenClaw Agent 本地，说明查询、预览、确认、拒绝和
  报告流程；
- **NAS OpenClaw release**：Skill、MCP 注册模板、安装器、验证器、manifest、checksum；
- **Agent token**：目标主机交互注入 OpenClaw SecretRef，不放进 NAS、Skill、ZIP、Git 或日志。

工具分层：

```text
observer
  get_fleet_status / get_accounts / get_positions / get_orders
  get_trades / get_strategy_status / get_project_progress

reporter
  observer + generate_report

executor_simulation（仅用户指定 agent_id）
  observer + preview_order / confirm_order / cancel_order_intent / get_intent_status
```

不提供 `redis_command`、任意 SQL、通用 RPC、shell、任意 HTTP 转发或直接券商 order API。

## 6. NAS 发布与本地安装

NAS 目录：

```text
\\192.0.2.236\truenas\kitling_bigqmt\
  releases\openclaw\candidate\<version>\
  releases\openclaw\stable\<version>\
  channels\openclaw.json
  reports\openclaw\<agent_id>\<date>\
  audit-replica\
  backups-encrypted\
```

部署动作：

```text
读取 NAS channel
→ 下载/复制 candidate 或 stable 到 125/113 本地 staging
→ 校验 manifest、SHA256、最低兼容版本
→ 备份当前本地 Skill/MCP 配置
→ 仅安装到目标 agent_id 的本地目录
→ openclaw mcp probe
→ openclaw skills check
→ 原子启用
→ 失败则回滚本地上一版本
```

权限规则：开发发布账号写 release；OpenClaw 仅读取 release；reporter 仅写自己的 reports 路径；下单
Agent 没有 NAS 发布写权限。

## 7. 实施阶段与步骤

### A. M01：本机配置与协议合同

位置：105 本机；不连接真实 Coordinator，不改 QMT。

1. 定义 `machine.local.json v2` schema。
2. 定义 heartbeat、snapshot、lease、intent、result 五类 JSON schema v1。
3. 统一 BigQMT、QMT、状态库、日志、备份、端口与 Coordinator endpoint 的路径解析。
4. 输出脱敏 effective-config 和配置哈希。
5. 配置损坏、路径越界、端口冲突时失败关闭。
6. 补充 secrets/runtime/cache 的 Git 忽略和 release 排除规则。
7. 通过单元测试；不得调用 QMT 或订单接口。

通过条件：所有入口使用同一份 effective config；任何错误配置不能回退开发机硬编码路径。

### B. M02：Coordinator 本机核心与 Fake Host

位置：105 本机开发测试；不部署 121。

1. 建 Coordinator SQLite WAL schema、migration、审计和恢复。
2. 建节点心跳、账户注册、lease、fencing token、epoch 状态机。
3. 建 intent 的 preview/confirm/claim/result 状态机。
4. 编写两个 Fake Host Agent 和故障注入测试。
5. 编写候选 Ubuntu release：wheelhouse、venv、systemd、backup/restore/preflight。

通过条件：两 Fake Host 不能同时取得同账户 lease；旧 token、重复请求、网络分区、Coordinator 重启均失败关闭。

### C. M04 前置：部署只读 Coordinator 到 121

需要 AP2 后执行。

1. 预检 121 的端口 18443、磁盘、NTP、Python、权限。
2. 创建无登录服务用户和 `/opt`、`/etc`、`/var/lib` 目录。
3. 安装离线 release 与 systemd 服务。
4. 创建私有 CA 和 IP-SAN TLS 证书；105 安装信任根。
5. 121 防火墙初期只允许 105 TCP 18443。
6. 启动服务，测试 `/healthz`、`/readyz`、重启恢复和本地 SQLite backup。
7. 从 105 浏览器登录 `https://192.0.2.121:18443/`。

通过条件：Coordinator 可以独立重启和恢复；没有 QMT/Redis/订单能力。

### D. M03：105 接入只读 Windows Host Agent

1. 在现有 `C:\BigQMT\work\kitling_bigqmt` 增加 Host Agent。
2. 连接 121 endpoint，上报 105 主机、Tray、QMT、Redis、Bridge、账户、持仓、委托、成交、策略和版本。
3. 初期 Host Agent 固定 `HEALTHY_READONLY`，不领取 intent。
4. 保留当前唯一 Tray 调度器；Host Agent 不能形成第二策略调度器。
5. Coordinator Dashboard 显示 105 的实时只读投影。

通过条件：关闭 Dashboard/Host Agent UI 不影响现有 Tray；Coordinator 不可达时本机策略不新增远程订单。

### E. M04：Fleet Control 与项目进度

1. 建 Fleet Overview、Nodes、Accounts、Strategies、Leases、Intents、Tests、Progress、Audit 页面。
2. 增加本机托盘“打开 Fleet Control”。
3. 页面展示来源、快照时间、新鲜度、配置哈希和版本。
4. 初期只实现暂停新增订单和只读查询；不实现主机迁移按钮。
5. 将 `progress/*.yaml/json` 投影为 `/fleet/progress`。

通过条件：控制台关闭不影响服务；所有按钮都有权限、审计和失败关闭路径。

### F. M05：125/113 OpenClaw 从 NAS 安装只读 MCP/Skill

需要 AP4 后执行。

1. 打包并发布 OpenClaw candidate 到 NAS。
2. 在 125/113 从 NAS 复制到本地，校验后安装 observer Skill/MCP 配置。
3. 配置 121 TLS 根证书和 observer token。
4. 先分别完成 MCP probe、Skill check、只读账户/持仓/策略/进度查询。
5. 对 113 已暴露的 OpenClaw 入口完成 TLS、token、pairing、allowlist 审计。
6. NAS 断线后复测本地已安装版本继续可用。

通过条件：手机可查询 105 的新鲜状态；所有未授权 Agent 查询/交易工具均被拒绝。

### G. M06：指定 Agent 的模拟订单意图

需要 AP5，并由用户在当前两名候选中选择唯一入口：`execution@198.51.100.113` 或
`xiaocai@192.0.2.125`，再提供允许下达指令的手机/频道身份。

1. 为该 Agent 单独创建 `executor_simulation` token 和严格 scope。
2. 只允许账户 `90000001`、允许策略、单笔/单日风险限额和整数手规则。
3. 实现手机 `preview_order` → 返回 `request_id` → 用户 `confirm_order`。
4. Coordinator 仅向 105 发放模拟 `ACTIVE_EXECUTOR` lease。
5. 105 Host Agent 本机再次预检，才交给现有 Execution Engine/Bridge/QMT。
6. 回传订单、成交、策略袖套、收益和审计状态。

通过条件：重复确认只产生一笔；过期、错误账户、旧 token、备用机、行情过期、资金/可卖不足、未知订单
均拒绝。正式账户没有任何 MCP 订单工具。

### H. M07/M08：稳定、125迁移、113备用和运维

1. 105 持续运行并完成多主机相关稳定性证据。
2. 125 先只读部署 QMT/Tray/Host Agent，与 105 对账。
3. 用户确认后执行 105 → 125 人工迁移：冻结 → 对账 → 撤销 105 lease → token 递增 → 125只读复核 →
   授权 125 → 105降级。
4. 113 保持只读，再单独演练 125 → 113 接管。
5. 运行 Coordinator 121 → 临时 Ubuntu/VPS 迁移演练：冻结、备份、停止旧实例、恢复、epoch+1、重新对账。
6. 生成 Windows/Ubuntu/OpenClaw 发布、更新、回滚、NAS 备份和灾难恢复报告。

通过条件：不会出现双主；旧主机与旧 Coordinator 无法凭缓存或旧 token 下单。

## 8. 测试矩阵

| 测试层 | 必测内容 | 是否触碰 QMT |
|---|---|---|
| Unit | config、schema、lease、fencing、intent、scope、SQLite | 否 |
| Fake integration | 双主、网络分区、重启、重复消息、旧 token | 否 |
| 121 deployment | systemd、TLS、备份、恢复、权限、端口 | 否 |
| 105 read-only | QMT/Redis/Bridge/Tray/策略快照上报 | 仅只读 |
| OpenClaw | NAS安装、MCP、Skill、Agent隔离、手机查询 | 仅只读 |
| Simulation execution | preview/confirm、下单、成交、撤单、恢复、核算 | 仅 90000001 |
| Failover/migration | 105→125、125→113、121→新宿主、防双主 | 模拟盘受控 |
| Production | 账户事实、恢复、监控、只读查询 | 仅只读 |

项目 `SIMULATION_VERIFIED` 的长期稳定性证据继续按原门禁累计；功能开发、Fake 测试和单次模拟验证不必
等待 20 个交易日才开始下一研发阶段。

## 9. 进度查询

当前依据：

```text
progress/status.md
progress/project_plan.yaml
progress/multi_host_program.yaml
progress/current_status.json
progress/latest_tests.json
progress/blockers.json
progress/history/
```

新增后统一支持：

```text
py scripts/manage/show_project_progress.py --program multi-host
GET https://192.0.2.121:18443/api/v1/progress
MCP bigqmt_get_project_progress
Fleet Control /fleet/progress
```

专项百分比仅计算 `PASSED/VERIFIED` 的权重；`IN_PROGRESS` 不计分；`BLOCKED` 必须显示解除条件；每个
`VERIFIED` 都必须关联版本、配置哈希、测试时间和证据文件。

## 10. 批准点

| 批准点 | 授权范围 | 不包含 |
|---|---|---|
| AP1 | M01/M02 本机开发、Fake Host 测试、候选包生成 | 121部署、QMT改动、订单 |
| AP2 | 121 只读 Coordinator 安装 | Host Agent、OpenClaw、订单 |
| AP3 | 105 只读 Host Agent 接入 | intent领取、下单 |
| AP4 | 125/113 从 NAS 安装 observer MCP/Skill | 下单 Agent、订单 |
| AP5 | 一个指定 agent_id 的模拟 preview/confirm | 正式账户和正式下单 |
| AP6 | 未来正式盘单独批准 | 不自动继承 AP1–AP5 |

## 11. 现在等待的确认

确认后从 **AP1** 开始：本机 machine config、协议合同、Coordinator core 与 Fake Host 测试。该批不修改
121，不接触 QMT，不改变现有 Tray，不发送订单。
