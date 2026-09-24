# BigQMT 分布式策略平台与 Coordinator 容器化整体执行方案

> 版本：Draft 1.0  
> 日期：2026-09-18  
> 状态：待批准执行  
> 项目主目录：`F:\kitling_QMT_work\kitling_bigqmt`  
> GitHub：`https://github.com/kitling-cax/Bigqmt`

## 1. 建设目标

建立一套将策略研发、回测、发布、部署、运行、交易、收益核算和审计分离的分布式 BigQMT 平台。

- `.105`：主要开发主机，负责策略研发、回测、版本发布、主分支维护和全局联调。
- `.125`、`.113`：主要策略运行主机，负责运行大QMT、Bridge、托盘、Host Agent 和策略实例。
- `.121`：Coordinator 宿主机，采用 Ubuntu VM + Docker Compose；当前端口 `18443` 保留，影子容器使用 `18666`。
- NAS：策略发布库、历史归档、数据库备份和跨主机迁移材料；不能成为 Windows 策略运行的实时依赖。
- 下单权限由每台 Windows 主机上的本地授权文件决定，不由 Coordinator 直接授予。
- Coordinator 负责策略目录、部署任务、唯一运行约束、状态监控、收益统计和审计，但不进入每笔订单的同步执行链。

## 2. 核心原则

### 2.1 权限与调度分离

- 本地授权 Key 决定主机是否具备指定账户的下单能力。
- Coordinator Assignment 决定某个策略实例应在哪台主机运行。
- 本地风险门禁决定当前订单能否真正发出。
- 三者同时满足时，策略才进入可执行模式。
- Coordinator 不保存 QMT 登录密码、授权 Key 明文或 Fact Secret 明文，只保存指纹、状态和到期时间。

### 2.2 离线可运行

- 策略包部署完成后，Windows 主机可以脱离 Coordinator 和 NAS 继续运行。
- 运行状态、订单、成交、持仓和净值先写本地 SQLite WAL/Outbox。
- Coordinator 恢复后，Host Agent 按幂等事件编号补传。
- NAS 中断不能导致托盘、大QMT、Bridge 或已运行策略停止。

### 2.3 稳定 Bridge、变化策略

- `BIGQMT_BRIDGE` 作为基础设施冻结，保持统一 RPC 协议和版本，例如当前 `0.3.26`。
- 策略版本在 Windows 策略宿主侧更新，通过本地 Redis RPC 调用 Bridge。
- 发布新策略通常不再修改或重建 QMT 内的 Bridge 策略。

### 2.4 先影子验证，再切换

- 当前 `18443` 服务继续运行。
- 容器化新系统先部署到 `.121:18666`。
- Host Agent 可双写只读事实到新旧端点，订单控制指令不双写。
- 数据核对通过后再将 `18443` 切换到容器版。

## 3. 总体架构

```text
.105 开发主机
  策略研发 -> 回测 -> 版本封装 -> GitHub -> NAS策略发布库
                                           |
                                           v
.121 Ubuntu VM + Docker Compose        Coordinator
  coordinator-api :18443/18666 <---- 策略目录/部署/监控/收益/审计
  coordinator-worker                   |
  PostgreSQL                            | 部署任务/事实回传
                                       v
                  +--------------------+--------------------+
                  |                    |                    |
              .105 托盘            .125 托盘            .113 托盘
              Host Agent           Host Agent           Host Agent
              策略宿主             策略宿主             策略宿主
              QMT/Bridge           QMT/Bridge           QMT/Bridge
              SQLite/Outbox        SQLite/Outbox        SQLite/Outbox
```

订单链路：

```text
策略实例 -> 本地风险检查 -> 本地授权检查 -> Redis RPC -> BIGQMT_BRIDGE
        -> QMT委托 -> 委托/成交回报 -> 本地账本 -> Host Agent -> Coordinator
```

Coordinator 不位于“策略信号到 QMT 委托”的同步必经路径。

## 4. 主机职责

### 4.1 `.105` 开发主机

- 维护 GitHub `main` 和正式发布标签。
- 策略开发、回测、数据质量检查和发布门禁。
- 生成不可变策略包、清单、SHA-256 和签名。
- 发布到 NAS 策略库。
- 可作为开发期运行主机，但长期运行与研发环境应隔离。

### 4.2 `.125`、`.113` 运行主机

- 同一套仓库通过各自主机分支处理兼容性修改，并通过 PR 回到 `main`。
- 运行大QMT/MiniQMT、双账户 Bridge、托盘、Host Agent 和策略宿主。
- 本地安装策略包，支持启动、停止、检查点和移除。
- 本地授权文件分别控制模拟账户与正式账户权限。
- 无授权时仍可运行只读、影子或信号验证模式。

### 4.3 `.121` Coordinator 主机

- 保留 Ubuntu VM，内部使用 Docker Compose。
- 运行 Coordinator API、Worker 和 PostgreSQL。
- 读取 NAS 策略目录并生成可部署版本列表。
- 接收主机心跳、策略状态、订单、成交、仓位和收益事实。
- 检测相同 `exclusive_group` 的重复运行。
- 发出部署、启动、停止和切换任务，但不直接提供本地交易授权。

### 4.4 GitHub 多主机协作流程

GitHub 是 `.105/.125/.113` 之间唯一的源码同步基线；NAS 不承担源码版本控制。

- `.105` 维护 `main`、正式发布标签、数据库 Migration 和公共配置模板。
- `.125` 使用独立主机分支，例如 `host/125`；由该机 VS Code（Claude）拉取代码、编译、测试并部署到本机。
- `.113` 使用独立主机分支，例如 `host/113`；由该机 VS Code（Claude）拉取代码、编译、测试并部署到本机。
- 主机兼容性修复先提交到各自主机分支，再通过 PR 合并回 `main`，不得让 `.125/.113` 直接覆盖 `main`。
- `.105` 审核并合并 PR 后执行整体回归，生成统一版本号、Git Tag 和发布包。
- `.125/.113` 仅从已批准的 Tag 或 Release 编译正式运行版本；普通开发提交不得自动覆盖正在运行的程序。

每台运行主机的标准过程：

1. 从 GitHub 获取最新远端状态。
2. 将本地主机分支 rebase/merge 到已批准的 `main` 或 Release Tag。
3. 读取 NAS 中该主机的私有部署说明和首次配置材料，但不把敏感内容提交到 Git。
4. 在 VS Code（Claude）中执行依赖检查、编译、自动测试和本机预检。
5. 先部署到候选目录，不直接覆盖正在运行的 EXE。
6. 停止旧托盘，备份本地状态，原子切换候选版本并启动。
7. 验证 QMT、Redis、Bridge、Dashboard、Host Agent、策略和 Coordinator 心跳。
8. 将构建清单、测试结果、部署证据和回滚点写入本机及 NAS 报告目录。
9. 如有通用修复，提交主机分支并创建 PR；机器私有路径、账户和密钥不进入提交。

推荐版本身份同时记录：

- `git_commit`
- `git_tag`
- `build_id`
- `host_id`
- `build_machine`
- `compiler/runtime_version`
- `package_sha256`
- `deployed_at`

这样 Coordinator 可以准确区分“源码已同步”“已经编译”“已经部署”和“正在运行”四种状态。

## 5. Coordinator 容器方案

| 服务 | 作用 | 外部端口 |
|---|---|---:|
| `coordinator-api` | API、网页、策略目录和控制面 | 18443 或 18666 |
| `coordinator-worker` | NAS扫描、收益计算、归档、过期清理 | 无 |
| `postgres` | 正式控制与收益数据库 | 不暴露到局域网 |
| `reverse-proxy` | 可选 HTTPS 与统一入口 | 后期启用 |

目录建议：

```text
/opt/kitling-bigqmt/
  compose/
    docker-compose.yml
    .env
  config/
    coordinator.json
    nas.json
  data/
    postgres/
    cache/
    logs/
  backups/
  releases/
```

要求：

- `.env`、数据库密码和签名私钥不进入 Git。
- PostgreSQL 活动数据卷必须位于 `.121` 本地磁盘，不放 SMB 共享。
- 容器使用健康检查、自动重启和固定镜像版本。
- `5432` 只允许 Compose 内部网络访问。

## 6. 策略发布与 NAS 目录

```text
\\<NAS_HOST>\truenas\kitling_QMT\
  strategy_library\
    catalog\
      strategies.json
      channels.json
    releases\
      <strategy_family_id>\
        <strategy_id>\
          <version>\
            <build_id>\
              manifest.json
              checksums.sha256
              strategy-package.zip
              release-notes.md
              backtest-summary.json
              compatibility.json
  strategy_runtime\
    canonical\<strategy_account_id>\
    checkpoints\
    reports\
    parquet\
  coordinator_backups\
    postgres\
    configs\
    audit\
```

每个策略包必须包含：

- `strategy_family_id`、`strategy_id`、`version`、`build_id`。
- `exclusive_group` 和默认策略账户定义。
- 兼容 Bridge 协议版本、Python 版本和操作系统。
- 回测摘要、参数文件、风险边界和迁移版本。
- 文件哈希与发布签名。

策略包发布后不可原地修改；修复必须生成新 `build_id`。

## 7. Windows 运行主机目录

```text
<LOCAL_BIGQMT_ROOT>\
  config\
    machine.local.json
    coordinator.local.json
  tray\
    BigQMT_<Profile>.exe
  strategy_host\
    catalog_cache\
    packages\
      downloading\
      verified\
      installed\
      archived\
    instances\<instance_id>\
    state\<instance_id>\strategy.sqlite3
    outbox\facts.sqlite3
    logs\
    evidence\
    backups\
  runtime_data\
```

本机敏感文件建议：

```text
<LOCAL_PROGRAM_DATA>\Kitling\BigQMT\
  authorization\
    simulation.execution.auth.json
    production.execution.auth.json
  secrets\
    host.fact.secret
  config\
    machine.local.json
```

首次部署可从 NAS 安全配置区导入，成功后保存到本机并脱离 NAS 运行。敏感文件不进入 Git、策略包或普通日志。

## 8. 托盘与 Host Agent 整合

每个账户或配置使用一个托盘 EXE，托盘内集成 Host Agent，不再额外要求用户启动独立后台程序。

该合并已在 `.105` 本机账户托盘源码中落地；`.125/.113` 通过 GitHub 分支编译部署相同版本后生效。

托盘功能：

- 启动与检测大QMT/MiniQMT。
- 检测并修复 Redis、Dashboard、Bridge 和策略宿主。
- 显示 QMT、Redis、Bridge、Dashboard、Host Agent 和快照新鲜度。
- 拉取 Coordinator 任务，下载并校验策略包。
- 管理策略安装、启动、停止、检查点和移除。
- 显示本地授权状态，但不显示 Key 内容。
- 将事实写入本地 Outbox 并异步上报。
- Coordinator 不可用时继续维持已运行策略。

## 9. 策略部署与切换流程

### 9.1 正常部署

1. `.105` 完成研发、回测与发布门禁。
2. 生成不可变策略包并发布到 NAS。
3. Coordinator Worker 扫描并登记策略版本。
4. 管理页面选择策略版本、目标主机和策略账户。
5. Coordinator 创建带幂等 ID 的部署任务。
6. 目标托盘拉取包到 `downloading`。
7. 校验签名、哈希和兼容性后进入 `verified`。
8. 原子安装到 `installed` 并创建策略实例。
9. 根据 Assignment、本地授权和风险状态决定执行、只读或影子模式。
10. 状态、日志、订单、成交和收益持续回传。

### 9.2 主机切换

1. 请求旧主机停止策略。
2. 旧主机完成订单状态收敛并生成 Checkpoint。
3. Coordinator 确认旧实例为 `STOPPED_CHECKPOINTED`。
4. Checkpoint 同步到 Coordinator/NAS 规范目录。
5. 新主机下载相同策略版本和 Checkpoint。
6. 使用相同 `strategy_account_id`，但生成新的 `instance_id` 和递增 `assignment_epoch`。
7. 新主机完成持仓、现金、未完成委托与 Broker 快照对账。
8. 对账通过后才允许启动。

旧主机无法确认停止时，不自动接管；强制接管必须人工明确确认并写入审计日志。

## 10. 防止重复执行

- 一个 `strategy_account_id` 同时只能有一个活动 Assignment。
- 一个 `exclusive_group` 默认只能在一台主机执行。
- Coordinator 检测冲突并发出严重告警。
- 本地托盘保存 Assignment epoch 和最后一次可用 Assignment。
- 本地授权 Key 仅代表交易能力，不代表某策略已被调度到本机。
- 发现冲突时，可将冲突实例降为只读或影子；不能删除历史事实。

## 11. Coordinator 数据库规划

目标数据库采用 PostgreSQL，按逻辑域划分：

- `catalog`：策略、版本、发布包、回测。
- `control`：主机、部署任务、命令、Assignment。
- `runtime`：策略账户、实例、状态历史、Checkpoint 和信号。
- `ledger`：订单、成交、现金、持仓、净值和绩效。
- `audit`：事实事件、幂等请求、操作审计。
- `ops`：任务状态、归档水位、告警和系统健康。

核心表：

- `catalog.strategies`、`catalog.strategy_versions`、`catalog.release_artifacts`、`catalog.backtest_runs`。
- `control.hosts`、`control.host_profiles`、`control.deployments`、`control.commands`、`control.command_results`、`control.strategy_assignments`。
- `runtime.strategy_accounts`、`runtime.strategy_instances`、`runtime.instance_status_history`、`runtime.checkpoints`、`runtime.strategy_signals`。
- `ledger.orders`、`ledger.order_updates`、`ledger.trades`、`ledger.cash_entries`、`ledger.position_entries`、`ledger.current_positions`、`ledger.broker_position_snapshots`、`ledger.nav_snapshots`、`ledger.daily_performance`。
- `audit.fact_events`、`audit.ingest_requests`、`audit.operator_actions`。

关键约束：

- 策略发布包、Host 事实和命令都具有唯一幂等 ID。
- Broker 成交使用账户、成交编号、交易日等组合去重。
- 活动 Assignment 对 `strategy_account_id` 和 `exclusive_group` 建立唯一约束。
- 账本事实追加写，修正通过冲正或新版本，不直接覆盖历史。

分层存储：

- PostgreSQL：控制面、当前状态、订单成交账本和近期收益查询。
- 主机 SQLite WAL：离线执行状态和 Outbox。
- NAS Parquet：长期订单、成交、净值、日志和报表归档。
- DuckDB：直接分析 Parquet 和生成研究报告。
- QuestDB 暂不作为必需组件，只有高频遥测规模确有需要时再引入。

## 12. 收益与策略子账户

- 每个策略使用稳定的 `strategy_account_id`，不等同于券商账户。
- 保存初始资金、策略现金、持仓成本、已实现/未实现收益和费用。
- 策略收益自动滚入策略权益，实现复利统计。
- 一个券商账户可承载多个策略子账户，但订单必须标记策略账户和实例。
- 每日使用 Broker 账户、持仓和成交快照与内部账本对账。

Dashboard 至少提供：

- 分策略净值曲线、收益率、最大回撤和基准对比。
- 当前仓位、现金、订单、成交和换手。
- 分主机、分账户和分策略运行状态。
- 版本、执行主机、Assignment epoch 和授权状态。
- 数据新鲜度、对账差异和异常告警。

## 13. 备份与恢复

- PostgreSQL 每日逻辑备份到 `.121` 本地，再复制 NAS。
- 每周完整备份；条件允许时启用 WAL 归档。
- NAS 保存策略包、Parquet 历史、配置备份和审计报告。
- Windows 主机备份 `strategy_host` 文件夹和 ProgramData 下的配置与授权；授权 Key 备份必须加密。
- 每季度执行一次恢复演练，验证新 Coordinator 和新 Windows 主机可恢复运行。

## 14. 安全边界

- QMT 密码、Fact Secret、授权 Key、Redis 密码和私钥不得进入 GitHub。
- 公共仓库只保留 `.example` 模板和变量说明。
- NAS 可以作为首次配置来源，但本地运行不得持续依赖 NAS。
- Coordinator API 先限制在内网；后续远程访问优先使用 Tailscale 或 VPN。
- OpenClaw/MCP 初期只开放查询工具；下单工具需单独设计双阶段确认、审计和权限范围。
- 正式账户下单能力必须独立授权，不能沿用模拟账户 Key。

## 15. 实施阶段

### P01：方案固化与接口冻结

- 固化策略包、Assignment、事实事件、Checkpoint 和授权状态结构。
- 固化 Bridge RPC `0.3.26` 兼容边界。
- 输出数据库 ERD 和 API 契约。

验收：JSON Schema、API 契约和迁移规则通过评审。

### P02：Coordinator 容器基础

- 在 `.121` 建立 Docker Compose 目录。
- 容器化 API、Worker 和 PostgreSQL。
- 先运行在 `18666`，保留 18443 原服务。

验收：重启、健康检查、日志、备份和回滚均通过。

### P03：PostgreSQL 与事实接入

- 建立初始 Migration。
- 迁移主机、账户、心跳和策略运行状态。
- 实现幂等事实接收和事件审计。

验收：重复上报不产生重复记录，数据库可从备份恢复。

### P04：托盘/Host Agent 统一

- 将 Host Agent 纳入托盘生命周期（`.105` 已完成本机编译验证）。
- 完成本地 Outbox、离线补传和任务拉取。
- `.105/.125/.113` 接入 18666 影子环境。

验收：三台主机在 Dashboard 可见；Coordinator 断线后本地继续运行，恢复后补传。

### P04A：`.125/.113` Git 编译部署闭环

- 为 `.125/.113` 固化主机分支命名、VS Code（Claude）接手文档和构建脚本。
- 建立候选目录、原子切换、版本清单、部署证据和一键回滚流程。
- 由 `.125` 和 `.113` 分别完成一次“拉取、编译、测试、部署、回传 PR”演练。

验收：两台主机可从同一批准 Tag 独立重建相同哈希的运行包；机器私有配置不进入 Git；失败时可恢复上一版本。

### P05：策略库与部署流程

- 建设 NAS 策略库、清单、签名和渠道文件。
- 完成托盘下载、校验、安装、启动、停止和移除。
- Coordinator 页面增加策略版本和目标主机选择。

验收：可将测试策略安全部署到指定主机，错误包不能安装。

### P06：v1.1.15 模拟盘无人值守

- 将 `v1.1.15｜5日｜U25无酒` 封装为首个正式策略包。
- 绑定模拟策略账户，使用模拟账户本地授权 Key。
- 验证信号、订单、成交、持仓、复利和重启恢复。

验收：模拟盘可独立运行和换仓，不依赖 Codex 在线。

### P07：收益账本与 Dashboard

- 建设订单、成交、仓位、净值和每日绩效账本。
- 补齐 Dashboard 专门页面和侧边栏跳转。
- 每日证据和报告归档 NAS。

验收：策略收益、曲线、持仓和成交可以按主机、账户、策略和版本查询。

### P08：主机迁移演练

- 先执行 `.125 -> .113` 或 `.105 -> .125` 的模拟策略迁移。
- 验证停止、Checkpoint、恢复、对账和收益连续性。

验收：同一策略账户净值连续，且任何时刻只有一个执行实例。

### P09：18443 切换与旧服务退役

- 新旧系统双读比对。
- 容器版接管 18443。
- 保留可回滚窗口，再退役 systemd 旧服务。

验收：切换不影响 Windows 已运行策略，回滚脚本实测有效。

### P10：正式账户准备

- 正式账户继续只读验证。
- 完成权限、风控、告警、灾备和人工确认流程后，另行审批正式账户下单授权 Key。

验收：未得到单独批准前，正式账户不能通过任何路径下单。

## 16. 本轮批准范围建议

建议本轮只批准 P01-P05：

- 允许改造 Coordinator、数据库、容器和托盘 Host Agent。
- 允许三台主机发送只读运行事实。
- 允许部署和管理测试策略包。
- 不改变正式账户当前权限。
- 不自动切换执行主机。
- 不新增 OpenClaw 下单能力。

P06 模拟账户交易、P08 强制迁移、P09 主服务切换和 P10 正式账户权限分别设置独立批准点。

## 17. 进度查询与证据

```text
progress/
  project_status.json
  milestones/
  daily_operations/
  evidence/
```

每个阶段必须记录：

- 完成项、未完成项和阻塞项。
- Git 提交、发布版本和部署主机。
- 自动测试、人工验证和回滚结果。
- Coordinator、托盘、Bridge 及策略运行证据。
- 数据库 Migration 版本和备份位置。

Coordinator Dashboard 提供同样的只读进度视图，但 Git 中的状态文件作为可审计基线。

## 18. 最终验收标准

- `.105` 可独立完成研发、回测和不可变发布。
- `.125/.113` 可从策略库安装并独立运行策略。
- 本地授权文件准确控制模拟/正式账户下单能力。
- Coordinator/NAS 中断不影响已运行策略。
- 相同策略账户不会在两台主机同时执行。
- 策略迁移后持仓、现金、订单和净值连续。
- Dashboard 可查询主机、账户、策略、版本、订单、成交、仓位和收益。
- PostgreSQL、NAS 归档和 Windows 本地状态均可备份恢复。
- 正式账户在单独批准前始终不可下单。

## 19. 批准后第一批动作

1. 只读盘点当前 18443、18666、Docker 和远端目录状态。
2. 固化策略包、事实事件、Assignment 和 Checkpoint Schema。
3. 新增 Compose、PostgreSQL Migration 和本地开发配置模板。
4. 在 18666 部署影子容器，不修改 18443。
5. 固化 `.125/.113` 的 Git 分支、VS Code（Claude）编译、候选部署和回滚流程。
6. 让 `.105` 先接入影子事实上报，再通过 GitHub 发布的批准版本接入 `.125/.113`。
7. 验证数据一致性后，再申请进入策略部署和 v1.1.15 模拟盘阶段。

---

本文件仅为待审批实施基线。未经单独批准，不启用正式账户下单、不执行强制主机接管、不退役当前 18443 服务。
