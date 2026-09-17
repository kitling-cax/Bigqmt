# 多主机 QMT、Coordinator 与 OpenClaw 总体研发规划

日期：2026-09-14  
状态：`PLANNED_PENDING_USER_CONFIRMATION / NO_RUNTIME_CHANGE`

## 1. 建设目标

在保留现有 BigQMT Bridge、双账户托盘、v1.1.15、策略袖套、SQLite 核算、Dashboard 和数据湖能力的
基础上，增加一套可以迁移、可以审计、可以防止双主下单的多主机控制层。

最终目标：

- QMT 与订单执行始终运行在 Windows；开发期间由本机 `192.0.2.105` 作为主力 QMT 和唯一模拟
  执行机候选，稳定后再人工迁移到其他 Windows；Codex 和 OpenClaw 都不是策略运行依赖；
- 同一账户可由两台 QMT 同时登录，但只有一台 `ACTIVE_EXECUTOR`；
- 手机可通过指定 OpenClaw Agent 查询账户，也可在授权后提交模拟订单；
- Coordinator 当前可部署在 `192.0.2.121`，以后能迁移到任意 Ubuntu VM 或外网 VPS；
- Windows、Ubuntu、OpenClaw 均由版本化安装包部署，可从 NAS 更新和回滚；
- 正式账户当前继续只读，未来正式下单另行授权，不由迁移或 Agent 配置自动开启。

## 2. 已确定的机器职责

| 地址 | 角色 | 当前建议 |
|---|---|---|
| `192.0.2.105` | PVE1 Win11 开发机/当前主力 QMT | 开发、构建、测试、发布并长期运行；开发期唯一模拟执行机候选 |
| `192.0.2.121` | PVE2 Ubuntu | Coordinator + Agent Gateway 首选宿主；已通过 SSH 与网络基线 |
| `192.0.2.125` | 物理 Win11 | 开发稳定后的首选迁移目标，接管前保持只读准备状态 |
| `198.51.100.113` | ESXi-C Win11 | 后续备用 QMT，保持 `STANDBY_READONLY` |
| `192.0.2.236` | TrueNAS | 发布源、数据交换、报告、审计和备份副本；不运行活动交易状态 |

`192.0.2.125` 的 OpenClaw 位于 WSL，`198.51.100.113` 的 OpenClaw 位于 Windows。两者都只作为中央
Agent Gateway 的客户端，因此安装位置不会决定 QMT 执行权。

## 3. 总体架构

```text
                         ┌────────────────────────────┐
手机 / OpenClaw Channel │ OpenClaw Agent             │
                         │ Skill + MCP client         │
                         └─────────────┬──────────────┘
                                       │ HTTPS / Agent token
                                       v
                    ┌──────────────────────────────────┐
192.0.2.121       │ Agent Gateway / BigQMT MCP       │
                    │ Query + Preview + Confirm        │
                    └──────────────┬───────────────────┘
                                   v
                    ┌──────────────────────────────────┐
                    │ Coordinator                      │
                    │ nodes/accounts/leases/epochs     │
                    │ intents/audit/progress           │
                    └──────────┬─────────────┬─────────┘
                         outbound poll   outbound poll
                              │               │
             ┌────────────────v───┐
192.0.2.105│ Windows Host Agent │  开发期唯一模拟 ACTIVE_EXECUTOR 候选
ACTIVE       │ Tray/Engine/Redis  │
             │ Bridge/QMT         │
             └────────────────────┘

192.0.2.125：稳定后的迁移目标 / 迁移前 READONLY_PREP
198.51.100.113：后续 STANDBY_READONLY

NAS 192.0.2.236：只接收 immutable release、报告、审计副本和备份
```

Windows 节点主动上报状态并拉取意图。Coordinator 不主动连接 Windows 下单端口；Redis、QMT RPC、
Dashboard 默认不向局域网开放。

### 3.1 初期访问方式与网络边界

第一版 Coordinator/Fleet Control 固定通过开发机浏览器访问：

```text
https://192.0.2.121:18443/
```

初期不要求 DNS、不配置公网映射、不做端口转发。Coordinator 的 TLS 证书必须包含 IP SAN
`192.0.2.121`，开发机先信任私有 CA。121 上的防火墙初期仅允许 `192.0.2.105` 访问 TCP 18443。
125、113 或 OpenClaw 接入前再按最小范围添加来源规则；跨网段 `198.51.100.113` 接入时再配置对应飞塔
策略。DNS `coordinator.bigqmt.internal`、Tailscale 与 VPS 迁移均后置，不是 M01–M04 的前提。

## 4. 组件职责

### 4.1 QMT Embedded Bridge

- 继续使用统一 `BIGQMT_BRIDGE` 代码；
- 封装账户、持仓、委托、成交、行情、下单与撤单；
- 最终仍要验证账户、环境、方法白名单、订单开关和 fencing token；
- Bridge 协议版本化，外部模块升级不应要求频繁修改 QMT 策略源码。

### 4.2 Windows BigQMT Tray / Host Agent

- 启动并监控 QMT、MiniQMT、Redis、Bridge、Dashboard 和策略流程；
- 读取本机权威 SQLite 和 QMT 快照；
- 向 Coordinator 上报脱敏心跳、账户、持仓、委托、成交、策略收益和版本；
- 主动拉取订单意图；只有有效 `ACTIVE_EXECUTOR` 租约才进入本机 Execution Engine；
- 本机最后复核账户、策略袖套、行情新鲜度、可用资金/数量、活动委托、幂等和令牌；
- 托盘或 Dashboard UI 关闭不能停止后台安全服务。

### 4.3 Coordinator

只负责协调，不直接调用券商：

- 节点注册和心跳；
- 每账户 `QUERY_PRIMARY`、`ACTIVE_EXECUTOR` 和 `STANDBY_READONLY`；
- 短租约、单调 `fencing_token` 和 `coordinator_epoch`；
- Agent 权限、订单意图、确认、领取、结果和审计；
- 冲突、离线、快照过期和迁移状态；
- 项目进度和发布版本的只读聚合。

### 4.4 Agent Gateway / MCP

- 是 OpenClaw 唯一允许调用的 BigQMT 网络入口；
- 暴露查询、预览、确认、取消意图和状态工具；
- 将 Agent token 映射为 observer、reporter 或 executor_simulation；
- 不暴露 SQL、Redis、通用 RPC、shell 或任意 URL 转发；
- MCP 是 OpenClaw 接口，Coordinator 与 Windows 节点内部使用版本化 HTTPS JSON 协议，避免内部
  安全机制依赖某个 Agent 框架。

### 4.5 OpenClaw Skill

- 识别账户、环境、证券代码、方向、数量和策略归属；
- 查询时显示数据来源、时间和新鲜度；
- 下单必须先 preview，再由用户确认同一个 `request_id`；
- 参数变化必须重新 preview；过期、歧义、网络中断或权限不足时拒绝；
- Skill 不保存 endpoint token、QMT 密码或券商凭据。

OpenClaw 已部署在 `192.0.2.125` 和 `198.51.100.113`，采用多 Agent 模式。发布包放入 NAS 后，两台
主机的安装器从 NAS 读取 immutable manifest/checksum，复制到各自本地 Agent 目录并完成 MCP probe
后启用；不从 SMB 共享盘实时加载代码。用户后续指定的单一 `agent_id` 才能获得
`executor_simulation` token；其余 Agent 即使可读取同一策略说明，也仅有 observer/reporter 权限。

### 4.6 Fleet Dashboard/Tray

建议新增只读页面：

- `/fleet/overview`：整体健康和关键异常；
- `/fleet/nodes`：每台主机 QMT、Redis、Bridge、Tray、版本、心跳；
- `/fleet/accounts`：账户事实、主查询源和快照时间；
- `/fleet/leases`：唯一执行主机、令牌、到期和接管状态；
- `/fleet/intents`：订单意图生命周期，不提供绕过门禁的直接按钮；
- `/fleet/strategies`：策略袖套、仓位、净值、收益与曲线；
- `/fleet/releases`：Windows/Coordinator/OpenClaw 当前与可回滚版本；
- `/fleet/tests`、`/fleet/audit`、`/fleet/progress`。

## 5. 核心状态模型

### 5.1 节点状态

`REGISTERING -> READONLY_SYNCING -> HEALTHY_READONLY -> ACTIVE_EXECUTOR`

异常进入 `DEGRADED / OFFLINE / CONFLICT / RECONCILING`。任何异常状态都不能新增订单。

### 5.2 账户运行阶段

`READ_ONLY -> SHADOW -> SIMULATION_LIVE -> PRODUCTION_LIVE`

阶段与主机租约分离。获得 `ACTIVE_EXECUTOR` 不代表获得正式盘交易许可。

### 5.3 订单意图状态

```text
DRAFT
 -> AWAITING_CONFIRMATION
 -> CONFIRMED
 -> READY_FOR_CLAIM
 -> CLAIMED
 -> SUBMITTED
 -> PARTIALLY_FILLED / FILLED
 -> CANCELED / REJECTED / EXPIRED / UNCERTAIN
```

只有券商真实成交可以修改策略现金和策略归属持仓。`UNCERTAIN` 必须先对账，不能自动重复下单。

## 6. 项目源码目录规划

现有目录继续保留；新增目录采用渐进式接入，不在一个版本中大规模移动旧文件。

```text
C:\BigQMT\work\kitling_bigqmt\
  AGENTS.md
  pyproject.toml

  src\kitling_bigqmt\
    existing modules...             # 现有 Bridge 客户端、执行、核算、数据湖
    contracts\                      # 协议对象、schema 解析、版本兼容
    coordinator\                    # 节点、账户、租约、epoch、intent、审计
    agent_gateway\                  # MCP server、鉴权、tool scopes
    host_agent\                     # Windows 心跳、快照上报、意图拉取
    fleet\                          # Fleet 状态投影和进度聚合
    release\                        # manifest、升级、回滚与兼容检查

  config\
    machine.local.json              # 唯一本机路径/端口/Coordinator 覆盖，不含权限密钥
    schemas\
      machine.local.schema.json
    contracts\
      node_heartbeat.v1.json
      account_snapshot.v1.json
      executor_lease.v1.json
      order_intent.v1.json
      order_result.v1.json
    policies\
      coordinator.yaml
      agent_roles.yaml
      simulation_limits.yaml
      production_readonly.yaml

  deploy\
    bridge\                         # QMT 内置 Bridge 发布物
    windows\                        # Windows Host/Tray 安装、服务、升级模板
    coordinator\                    # Ubuntu wheelhouse、systemd、迁移模板
    openclaw\                       # Skill、MCP 注册和安装包模板
    nas\                            # 发布 channel 和权限说明

  scripts\
    manage\                         # 安装、启动、状态、迁移、备份
    release\                        # 构建、签名、checksum、发布、回滚
    test\                           # 网络、故障、QMT、OpenClaw 验收入口

  tests\
    unit\
    integration\
    contracts\
    fault_injection\
    acceptance\
    fixtures\

  openclaw\bigqmt-operator\
    SKILL.md
    references\

  runtime_data\                     # 本机运行状态，不进入发布源码
    state\<profile>\
    audit\<profile>\<date>\
    evidence\
    outbox\
    cache\
    backups\

  progress\
    project_plan.yaml
    multi_host_program.yaml
    current_status.json
    latest_tests.json
    blockers.json
    history\

  dist\                              # 生成的不可变发布包
```

必须补充 `.gitignore`，排除 `machine.local.json` 的本机变体、凭据、runtime_data 活动库、日志、缓存、
构建产物和 QMT 下载数据；同时保留脱敏 example/schema。

## 7. 各运行环境目录

### 7.1 开发机 `192.0.2.105`

保持现有目录：

```text
C:\BigQMT\work\kitling_bigqmt
C:\BigQMT\work\国金QMT交易端模拟
C:\BigQMT\work\国金证券QMT交易端
```

只由开发机构建 release；运行机不直接修改 release 内容。

### 7.2 Windows QMT 运行机 125/113（稳定后迁移目标）

```text
E:\kitling_bigqmt\
  releases\<version>\
  current.json                      # 当前版本指针，避免依赖管理员符号链接
  config\machine.local.json
  runtime_data\
    state\simulation\
    state\production\
    audit\
    logs\
    outbox\                         # Coordinator/NAS 断开时本地排队
    cache\
  updates\staging\
  backups\

E:\国金QMT交易端模拟\
E:\国金证券QMT交易端\
```

QMT 密码使用 Windows Credential Manager；Agent/节点私钥使用 DPAPI/受限 ACL。更新器必须保留
`machine.local.json`、凭据和 runtime_data。

### 7.3 Coordinator Ubuntu `192.0.2.121` 或未来 VPS

```text
/opt/bigqmt-coordinator/releases/<version>
/opt/bigqmt-coordinator/current
/etc/kitling-bigqmt-coordinator/coordinator.yaml
/etc/kitling-bigqmt-coordinator/tls/
/var/lib/kitling-bigqmt-coordinator/coordinator.sqlite3
/var/lib/kitling-bigqmt-coordinator/backups/
/var/lib/kitling-bigqmt-agent-gateway/
```

日志优先 journald。服务分别使用无登录、无 sudo 的 `bigqmt-coordinator` 与 `bigqmt-gateway` 用户。

### 7.4 NAS 发布与交换目录

规划统一创建：

```text
\\192.0.2.236\truenas\kitling_bigqmt\
  releases\
    windows\candidate\<version>\
    windows\stable\<version>\
    coordinator\candidate\<version>\
    coordinator\stable\<version>\
    openclaw\candidate\<version>\
    openclaw\stable\<version>\
  channels\
    windows.json
    coordinator.json
    openclaw.json
  reports\openclaw\<agent_id>\<date>\
  audit-replica\<component>\<date>\
  backups-encrypted\<component>\<date>\
  exchange\inbox\
  exchange\outbox\
  data-lake\
```

`channels/*.json` 只指向不可变 release。目标机先复制到本地 staging，验证 SHA256/manifest 后原子切换；
绝不从 SMB 直接运行程序、Redis、SQLite 或策略。

OpenClaw release 目录补充为：

```text
releases\openclaw\candidate\<version>\
  skill\
  mcp\
  install\
  manifest.json
  checksums.sha256
releases\openclaw\stable\<version>\
channels\openclaw.json
```

开发发布账号可写 candidate/stable；OpenClaw 主机只能读 release；报告 Agent 只能写
`reports\openclaw\<agent_id>\`。下单 Agent 不获得 NAS 发布写权限。

## 8. `machine.local.json` 规划

只包含机器相关内容：

- `machine_id`、角色提示；
- BigQMT project/runtime/cache/log/backup 根目录；
- 模拟与正式 QMT 根目录；
- Redis、Dashboard、QMT ready 端口；
- Coordinator/Agent Gateway 稳定 URL、CA 路径；
- NAS release source 与本地 staging 路径。

不包含：

- QMT、Redis、OpenClaw、Agent 密码或 token；
- `orders_enabled`；
- `ACTIVE_EXECUTOR`；
- 正式盘授权；
- 策略准入和资金上限。

配置存在但损坏时必须失败关闭；不能悄悄回退到开发机 F 盘。每次启动输出脱敏 effective-config 与
SHA256，以便比较两台机器实际加载的配置。

## 9. 研发里程碑与顺序

详细权重见 `progress/multi_host_program.yaml`。

| 里程碑 | 权重 | 当前状态 | 主要结果 |
|---|---:|---|---|
| M00 架构与网络基线 | 5% | PASSED | 拓扑、121 SSH、跨网段证据 |
| M01 可迁移配置与协议 | 10% | IN_PROGRESS | machine schema、五类 v1 contract、路径收口 |
| M02 Coordinator Core | 15% | NOT_STARTED | lease、fencing、epoch、intent、审计、systemd 包 |
| M03 Windows Host Agent | 15% | NOT_STARTED | 双节点只读上报、拉取、本机复核 |
| M04 Fleet 监控与进度 | 10% | NOT_STARTED | 中央托盘、Dashboard、进度接口 |
| M05 OpenClaw MCP+Skill | 10% | NOT_STARTED | 手机只读查询、安装包、角色限制 |
| M06 模拟远程订单意图 | 15% | NOT_STARTED | preview/confirm、模拟盘闭环 |
| M07 主备接管与迁移 | 10% | NOT_STARTED | 125→113、121→其他 Ubuntu/VPS、防双主 |
| M08 发布运维与验收 | 10% | NOT_STARTED | NAS 更新、回滚、备份、灾难演练 |

新多主机专项当前严格进度为 **5%**。现有代码虽然可复用，但在完成新协议适配和多主机测试前不计入
专项完成度。

## 10. 测试规划

### 10.1 单元测试

- lease 唯一性、续租、到期、时钟偏差；
- fencing token 单调增加和旧 token 拒绝；
- coordinator_epoch 重启/迁移失效；
- intent 参数校验、幂等、过期、取消和状态转换；
- Agent scope、账户/环境隔离；
- effective-config、路径越界、端口冲突和损坏配置；
- 真实成交驱动袖套，重复成交去重。

### 10.2 无 QMT 集成测试

使用两个 Fake Host Agent：

- 同账户同时请求执行权；
- 心跳丢失、网络分区、迟到消息、乱序和重复领取；
- Coordinator 重启、SQLite WAL 恢复、旧主继续发送；
- Agent preview 后篡改参数；
- Gateway/Coordinator/Host 任一层返回超时或未知状态。

此层必须证明没有真实 QMT、Redis 或券商调用。

### 10.3 `192.0.2.121` 部署测试

- clean install、systemd 启动、重启自恢复、非 root 权限；
- TLS、Agent token、节点证书与防火墙；
- 数据备份、恢复、磁盘满、NTP 异常；
- NAS 中断不影响协调；审计副本恢复后继续同步；
- 卸载和回滚不删除活动数据库。

### 10.4 Windows Host Agent 测试

- 第一阶段在现有开发机 105 接入真实 Host Agent，125/113 暂不接管；
- 稳定后再让 125/113 分别以只读方式运行 Tray/Host Agent；
- QMT、Redis、Bridge、账户、持仓、委托、成交、行情和策略状态上报；
- 两台同账户数据差异检测；
- standby 无订单 RPC、无自动策略恢复、无补单；
- 重启 Windows、QMT、Bridge、Redis、Tray 后先对账再恢复只读；
- 外部不能直接访问 Redis/QMT RPC。

### 10.5 OpenClaw 测试

- Skill 能被发现，MCP probe/status 正常；
- observer 无 preview/confirm，reporter 只能写指定 NAS 报告目录；
- executor_simulation 只能访问模拟账户；
- 未授权手机用户、群消息、转发/引用内容和 prompt injection 不获得交易能力；
- 查询显示来源、时间和新鲜度；过期时回答不可确认；
- `198.51.100.113:18789` 完成绑定、TLS/token、pairing/allowlist 安全审计。
- 从 NAS candidate/stable 读取、manifest/SHA256 验证、本地安装、回滚和 NAS 断线后的持续运行；
- 多 Agent 路由：只有用户指定的 `agent_id` 出现 preview/confirm 工具，所有其他 Agent 均被网关拒绝。

### 10.6 模拟盘订单测试

- 正确的股票代码、买卖方向、100 股整数手、限价规则；
- preview 与 confirm 两步；过期确认和参数变化拒绝；
- 重复手机消息和重复 confirm 只产生一个订单；
- standby、旧 fencing token、错误账号、行情过期、资金不足、不可卖、活动委托存在时拒绝；
- 全成、部成、撤单、拒单、超时、状态未知和重启恢复；
- 委托、成交、券商持仓、策略袖套和手机结果最终一致。

模拟盘功能开发和单次订单验证无需等待 20 个交易日；但整个项目标记 `SIMULATION_VERIFIED` 仍按灵魂
文件要求累计稳定性证据，稳定性观察与后续研发并行进行。

### 10.7 接管与迁移测试

- 开发期间只有 105 可以成为模拟执行机，125/113 均不能下单；
- 稳定后先把 125 以只读方式接入，再冻结 105、对账并人工迁移执行权到 125；
- 105 恢复或继续运行时旧 token 被本机和 Coordinator 双重拒绝；
- 后续再单独演练 125 到 113 的人工备用接管；
- 迁移 121 到临时 Ubuntu/VPS：冻结、备份、停止旧机、恢复、epoch+1、稳定 URL 切换；
- 故意重新启动旧 Coordinator，节点仍拒绝旧 epoch；
- 回迁和版本回滚同样通过。

### 10.8 正式账户

只做账户、持仓、委托、成交、行情、节点和恢复的只读验证。OpenClaw 不创建 production executor
token，Dashboard 不提供正式交易按钮。本规划不包含正式盘下单授权。

## 11. 发布、更新与回滚

每个发布物必须具有：

- 版本号、Git/源哈希、schema 版本、最低兼容版本；
- 完整 manifest、逐文件 SHA256、构建时间；
- 数据库迁移版本与回滚限制；
- candidate/stable channel；
- Windows、Coordinator、OpenClaw 独立版本，不强制同步升级；
- 升级前预检和本地备份；失败后自动回旧 release，执行权保持关闭。

Bridge 协议至少兼容前一个 Host Agent 版本。涉及订单 schema 的破坏性变化必须新建版本，不原地覆盖。

## 12. 进度查询设计

### 12.1 当前已有文件

- `progress/status.md`：给人看的最新摘要；
- `progress/project_plan.yaml`：全项目 P01–P28 状态；
- `progress/multi_host_program.yaml`：本专项 M00–M08、权重、门禁；
- `progress/current_status.json`：当前运行、权限和下一门禁；
- `progress/latest_tests.json`：最近测试和证据；
- `progress/blockers.json`：阻塞原因、负责人和解除条件；
- `progress/history/`：不可覆盖的历史快照。

### 12.2 计划新增查询入口

```text
py scripts/manage/show_project_progress.py
py scripts/manage/show_project_progress.py --program multi-host --json
GET /api/v1/progress
MCP bigqmt_get_project_progress
Dashboard /fleet/progress
```

所有入口读取同一组 progress 文件，不各自计算一套状态。进度百分比只按 `PASSED/VERIFIED` 权重计算；
`IN_PROGRESS` 不计完成，`BLOCKED` 必须展示解除条件，`VERIFIED` 必须链接测试时间、版本、配置哈希和
证据文件。

每次研发批次结束必须同时更新：

1. 源码与测试；
2. `latest_tests.json`；
3. `multi_host_program.yaml` 对应门禁；
4. `current_status.json`；
5. `status.md`；
6. `history/<timestamp>_<event>.json`；
7. 若生成发布物，再更新 manifest/checksum，但不自动升 stable。

## 13. 用户确认点

后续分六次授权，不一次性扩大权限：

1. **AP1**：确认本方案，开始 M01/M02 本机开发和 Fake Agent 测试；
2. **AP2**：允许在 `192.0.2.121` 安装只读 Coordinator；
3. **AP3**：先允许在现有开发机 105 接入 Host Agent；稳定后另行允许 125/113 只读接入；
4. **AP4**：允许 125/113 上现有多 Agent OpenClaw 从 NAS release 安装只读 MCP/Skill；
5. **AP5**：给出确切 `agent_id` 与手机/频道身份，并允许该一个 Agent 获得模拟盘 preview/confirm；
6. **AP6**：未来正式盘交易单独授权，本规划不预先放行。

## 14. 确认后第一批工作

确认后先推进 M01/M02，不碰真实订单：

1. 建立五类 JSON Schema 和兼容规则；
2. 完成 `machine.local.json` v2 严格 schema、effective-config 和路径硬编码审计；
3. 建 Coordinator SQLite schema、lease/fencing/epoch 状态机；
4. 用两套 Fake Host Agent 完成双主、重启、网络分区测试；
5. 生成 `192.0.2.121` 的候选安装包和 preflight 报告，但等 AP2 后才远程安装。

本文件是规划确认稿。本轮不安装服务、不改远程主机、不更改 QMT/Bridge/Tray、不切换执行权、不发送
订单。
