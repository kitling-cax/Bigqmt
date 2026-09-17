# OpenClaw MCP/Skill 交付与可迁移 Coordinator 方案

日期：2026-09-14  
状态：`DESIGN_CONFIRMED / COORDINATOR_HOST_SSH_VERIFIED / NO_SERVICE_INSTALLED`

## 1. 交付决策：MCP 与 Skill 都需要

只做 Skill 不够。Skill 是给 Agent 的操作说明，不能凭空提供受类型约束、可鉴权的账户查询和订单
意图能力。只做 MCP 也不够，Agent 不知道项目的环境选择、查询新鲜度、二次确认和失败关闭规则。

最终交付拆为：

1. `BigQMT MCP Server`：由中央 Agent Gateway 托管，暴露严格的结构化工具；
2. `bigqmt-operator` OpenClaw Skill：说明何时调用工具、如何预览/确认、如何解释状态以及何时拒绝；
3. `OpenClaw install bundle`：Skill 目录、MCP 注册模板、权限 profile、安装/检查脚本和 checksum；
4. 每台 OpenClaw 单独注入的 Agent token：不在 Skill、ZIP、NAS 或 Git 中保存。

用户已确认 OpenClaw 已部署于 `192.0.2.125` 与 `198.51.100.113`，并采用多 Agent 模式。NAS 是两台
OpenClaw 主机读取 release 的发布源；MCP Server 本身仍运行在 Coordinator/Agent Gateway，不运行在 NAS。

OpenClaw 官方定义也是：tool/MCP 提供可调用的类型化功能，Skill 提供可重复工作流和约束。Skill 可作为
本地目录安装；Control UI 可导入含根目录 `SKILL.md` 的归档。安装包不能把交易凭据写入
`SKILL.md`。

## 2. MCP 工具边界

首批只读工具：

- `bigqmt_get_fleet_status`
- `bigqmt_get_accounts`
- `bigqmt_get_positions`
- `bigqmt_get_orders`
- `bigqmt_get_trades`
- `bigqmt_get_strategy_status`
- `bigqmt_get_intent_status`

模拟交易工具：

- `bigqmt_preview_order`
- `bigqmt_confirm_order`
- `bigqmt_cancel_order_intent`

不提供通用 RPC、Redis、SQL、shell、任意 URL 转发或直接券商下单工具。`preview` 只创建短时待确认对象；
`confirm` 必须引用原 `request_id`，不能改变证券、方向、数量或账户。模拟和正式使用完全不同的 Agent
角色与 token；当前不建立正式交易角色。

## 3. “扔给 OpenClaw”后的安装形态

计划发布目录：

```text
openclaw-bigqmt-bundle-<version>/
  manifest.json
  checksums.sha256
  README_INSTALL.md
  skill/
    SKILL.md
    references/
      order_confirmation.md
      query_freshness.md
      failure_policy.md
  mcp/
    server.example.json
    observer.tools.json
    reporter.tools.json
    executor_simulation.tools.json
  install/
    install-openclaw.ps1
    install-openclaw.sh
    verify-openclaw.ps1
    verify-openclaw.sh
```

安装脚本只完成 Skill 复制、MCP endpoint 注册和健康探测。Agent token 必须在目标机交互输入或通过
OpenClaw SecretRef 配置。交付后分别执行 `openclaw mcp probe/status` 与 `openclaw skills check`；不得仅凭
目录存在宣称安装成功。

NAS 到 Agent 的安装流程：

```text
NAS immutable release
  -> 本机 installer 读取 channel + manifest + SHA256
  -> 复制到本机 versioned staging
  -> 写入该 Agent 自己的 Skill/MCP 配置目录
  -> MCP probe + Skill check
  -> 原子启用本地版本
```

不让 OpenClaw 从 SMB 路径直接加载活跃 Skill、脚本或 MCP runtime。这样 NAS 临时离线、共享更新或
权限变化不会中断已运行 Agent；失败时保留上一个本地已验证版本。

### 3.1 多 Agent 权限模型

| Agent 类别 | MCP 权限 | NAS 权限 | 交易权限 |
|---|---|---|---|
| `qmt-observer` | 账户、持仓、委托、成交、策略、进度查询 | 无或只读 release | 无 |
| `qmt-reporter` | observer + 已审核报告生成 | 仅 reports 路径写入 | 无 |
| 用户指定的 `qmt-executor-simulation` | observer + preview/confirm/cancel intent | 只读 release | 仅模拟账户、仅确认后的意图 |
| `qmt-executor-production` | 不创建 | 不创建 | 当前禁止 |

执行 Agent 必须由用户给出确切的现有 `agent_id`、所属 OpenClaw 主机以及可接受指令的手机/频道身份。
每个 Agent 使用独立 token，token 的 scope 在 Agent Gateway 强制验证；即便其他 Agent 获得同一个
`SKILL.md` 文件，也不会得到 confirm 工具或订单能力。

## 4. Coordinator 可迁移设计

Coordinator 的实现不绑定 `192.0.2.121`、PVE、NAS 或特定云厂商。初期固定使用直接 IP endpoint
`https://192.0.2.121:18443`，不以 DNS 为部署前提；证书包含该 IP 的 SAN。多主机稳定后再将 Windows
节点切换到稳定 URL，例如 `https://coordinator.bigqmt.internal`，底层可由局域网 DNS、Tailscale MagicDNS
或 VPS FQDN 指向当前宿主。

Coordinator 发布包：

```text
kitling-bigqmt-coordinator-<version>/
  manifest.json
  checksums.sha256
  app/
    *.whl
  wheelhouse/
    *.whl
  config/
    coordinator.example.yaml
  systemd/
    kitling-bigqmt-coordinator.service
    kitling-bigqmt-agent-gateway.service
  scripts/
    install.sh
    preflight.sh
    backup.sh
    restore.sh
    migrate-out.sh
    migrate-in.sh
    verify.sh
  migrations/
```

首版以 Python 3.12 venv + systemd 为权威部署方式，wheelhouse 支持离线安装；Docker Compose 作为后续
等价包装，不成为迁移前提。目录固定为：

- 程序：`/opt/bigqmt-coordinator/releases/<version>`；
- 当前版本软链接：`/opt/bigqmt-coordinator/current`；
- 非密配置：`/etc/kitling-bigqmt-coordinator/coordinator.yaml`；
- 凭据/私钥：systemd credentials 或 root-only `/etc/.../secrets.env`；
- 活动状态：`/var/lib/kitling-bigqmt-coordinator/`；
- 日志：journald；审计副本异步复制 NAS。

## 5. 迁移协议

不能简单复制目录后让新旧两个 Coordinator 同时运行。迁移必须：

1. 进入 `MIGRATION_FREEZE`，停止发放/续租执行权；
2. Windows 节点全部确认 `STANDBY_READONLY`；
3. 使用 SQLite 在线备份导出状态，生成 manifest 和 SHA256；
4. 停止旧 Coordinator；
5. 在新 Ubuntu/VPS 恢复配置、状态、CA/节点身份材料；
6. 增加 `coordinator_epoch`，使所有旧租约和 fencing token 永久失效；
7. 更新稳定 DNS/Tailscale 名称指向；
8. 节点重连、只读对账通过后，人工重新授予唯一模拟 `ACTIVE_EXECUTOR`。

NAS 只能保存迁移包和加密备份，不能让两个 Coordinator 共同打开 NAS 上的 SQLite。如果未来要求真正
高可用而不是人工迁移，需升级为 PostgreSQL/etcd/Raft 等明确的一致性方案，不能用 SMB 锁拼接双主。

## 6. `192.0.2.121` SSH 验证结果

- SSH 登录成功，未保存口令；
- Ubuntu 24.04.4 LTS，KVM/QEMU，4 vCPU；
- 内存 7.7 GiB，可用约 7.0 GiB；Swap 4 GiB；
- 根盘 125 GiB，可用 108 GiB；
- Python 3.12.3、systemd 正常；时区 Asia/Shanghai，NTP 已同步；
- 能反向访问 `192.0.2.105`、`192.0.2.125`、`198.51.100.113` 和 NAS；
- NAS 445、两台 QMT 主机 3389 从该 VM 可达；
- 当前没有 Docker、Podman、curl，监听端口仅观察到 SSH 22；尚未安装任何 Coordinator 服务。

硬件和网络资源足够，判断为 `SUITABLE_FOR_COORDINATOR_IMPLEMENTATION`。证据：
`runtime_data/evidence/network/coordinator_candidate_192_168_1_121_20260914.json`。

## 7. 下一实施门禁

1. 先实现 Coordinator 协议、SQLite schema、lease/fencing 与纯本地测试；
2. 再生成 121 的安装包并只部署只读心跳；
3. 两台 Windows Host Agent 接入，只上报状态，不领取订单；
4. 完成 OpenClaw 只读 MCP + Skill 安装包；
5. 手机查询验收；
6. 最后才开放指定 Agent 的模拟订单预览/确认，并做双主和迁移演练。

本次没有安装远程软件、修改 Ubuntu、写入 NAS、改变 QMT 或发送订单。
