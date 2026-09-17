# QMT 长期主机、OpenClaw 手机入口与局域网评估

日期：2026-09-14  
状态：`ASSESSMENT_COMPLETE / HOST_SEQUENCE_SUPERSEDED_BY_DOC_121 / NO_RUNTIME_CHANGE`

> 后续用户决定：开发期间由 `192.0.2.105` 作为主力 QMT 和唯一模拟执行机候选，稳定后再迁移到
> `192.0.2.125`，`198.51.100.113` 作为备用。本文对 125/113 的硬件评估仍有效，但“立即以 125 为主”
> 的时间顺序已由 `docs/121_development_host_primary_execution_and_later_migration_decision_2026-09-14.md`
> 覆盖。

## 结论

1. 长期主 QMT 首选物理 Win11 `192.0.2.125`，备用 QMT 首选 ESXi-C Win11
   `198.51.100.113`。原因是大 QMT 必须运行于 Windows，而物理机比虚拟机少一层 ESXi、宿主机和虚拟
   网络故障域。OpenClaw 位于 WSL 不改变这个排序，因为 OpenClaw 不应成为策略运行依赖。
2. 两台 Windows 均运行本机 BigQMT Tray、Host Gateway、Execution Engine、Redis 与 QMT Bridge。
   同一账户只能由 Coordinator 授予一台 `ACTIVE_EXECUTOR`；备用机固定为 `STANDBY_READONLY`。
3. 手机通过 OpenClaw 查询和提交订单意图是可行的，但 OpenClaw 不能直接访问 QMT RPC、Redis、
   SQLite、券商密码或通用下单函数。两台 OpenClaw 都只调用中央 Agent Gateway 的窄接口。
4. 初版把 Coordinator Service 与 Agent Gateway 作为两个独立服务部署在 PVE2 新建的小型 Ubuntu VM。
   PVE2 现有 `192.168.1.120` Qlib VM 可用于短期联调，不建议长期混载。新 VM 的固定 IP 必须先做地址
   冲突检查后再确定。
5. NAS 只保存不可变发布包、报告、审计副本和数据交换文件，不承担在线心跳、订单队列、租约或活动
   SQLite。实测共享根可访问，但规划的 `\\192.0.2.236\truenas\kitling_bigqmt` 尚不存在；当前存在
   的相关目录是 `\\192.0.2.236\truenas\kitling_QMT`，发布根需在实施阶段统一。

## 推荐数据流

```text
手机聊天/移动端
      |
      v
OpenClaw（125/WSL 或 113/Windows，均只是受限客户端）
      |
      v  HTTPS + 独立 Agent 身份 + 请求签名/TTL
Agent Gateway（PVE2 Ubuntu）
      |                    \
      | 查询                \ 订单意图
      v                      v
只读聚合快照          Coordinator / Intent Queue
                              |
                              v  仅 ACTIVE_EXECUTOR 可领取
        125 Windows Host Agent 或 113 Windows Host Agent
                              |
                    本机风险复核 + fencing token
                              |
                     Redis(127.0.0.1) -> Bridge -> QMT
```

Windows Host Agent 主动向 Coordinator 上报脱敏快照、心跳并拉取订单意图。这样不需要从 WSL 或其他
网段直接开放 QMT、Redis、Dashboard 端口，也避免把 OpenClaw 安装位置与交易执行位置强耦合。

## 两种 OpenClaw 部署的差异

### `192.0.2.125`：OpenClaw 位于 WSL

- 优点：与 Windows/QMT 有天然进程边界，适合把 Agent 约束成只访问一个 HTTPS 工具；物理机本身适合
  长期 QMT。
- 风险：Windows 重启后 WSL Gateway 是否常驻、WSL NAT/镜像网络、睡眠和用户登录状态都需要验收。
- 设计要求：BigQMT 仍由 Windows 托盘/服务独立启动；WSL 停止不得影响 v1.1.15。不要让 OpenClaw
  直接挂载或修改 QMT、凭据和 BigQMT 状态目录。手机若使用 Telegram/WhatsApp 等通道，Gateway 通过
  出站连接工作，不需要对局域网开放 18789。

### `198.51.100.113`：OpenClaw 位于 Windows

- 优点：本机服务管理和网络路径更直接，避免 WSL 生命周期与 NAT 差异。
- 风险：Agent 与 QMT 位于同一 Windows 安全域；若给予 shell、文件或管理员权限，影响面更大。
- 设计要求：OpenClaw 使用独立非管理员 Windows 用户；交易能力只通过 Agent Gateway 的特定工具暴露，
  不提供通用 shell/RPC 代理。实测 `http://198.51.100.113:18789/` 从开发机以明文 HTTP 返回 `200 OK`；
  这不证明工具/API 未鉴权，但证明页面入口已跨网段暴露。需检查强认证、来源限制和 TLS；若不需要局域网
  直接访问，应改回 loopback 或仅绑定 Tailscale 地址。

OpenClaw 官方当前建议 Gateway 默认只绑定 loopback，并对私聊采用 pairing/allowlist；一个 Gateway 是
一个信任边界。两台现有 Agent 可以保留，但每台必须有独立 `agent_id` 和 token。若两台使用同一个
Telegram Bot 的轮询 token，不得同时作为活动收件端；应指定一个手机入口，另一台仅作为备用或使用
不同 Bot/Channel。

## 手机查询与下单边界

### 查询

允许查询中央只读快照：账户、持仓、活动委托、成交、行情时间、策略袖套、收益曲线、节点健康和当前
执行权。每条答复都要显示来源主机、快照时间、环境和新鲜度。快照过期时明确回答“不可确认”，不得把
旧数据包装成实时数据。

### 下单

OpenClaw 只产生结构化 `order_intent`：

- `request_id`、`agent_id`、手机用户/频道身份；
- `account_id`、`environment`、`strategy_id`；
- 证券代码、方向、数量/目标金额、限价规则；
- 创建时间、到期时间、理由和确认摘要。

模拟盘建议采用“预览 -> 用户确认 request_id -> 执行”的两步流程。正式盘未来即使获批，也必须另行
启用正式 Agent 角色、单笔/日累计限额、短 TTL 和二次确认；不能沿用模拟权限。Agent Gateway、
Coordinator 和本机 Execution Engine 三层都要验证账户、权限、租约与 fencing token。任一层失联、
状态不确定或快照过期，拒绝新订单。

## 2026-09-14 网络实测

探测源为开发机 `192.0.2.105`，默认网关 `192.0.2.99`。这证明从开发机到目标的单向可达性，不等于
目标机反向路径、应用鉴权或服务健康。

| 节点 | 结果 | 关键证据 |
|---|---|---|
| `192.0.2.125` 物理 Win11 | 可达 | 6/6，平均 0.83 ms；3389/445/22 可连 |
| `198.51.100.113` ESXi-C Win11 | 跨网段可达 | 6/6，平均 0.33 ms；3389/445/18789 可连 |
| `192.0.2.236` TrueNAS | 可达 | 6/6；445/80/443 可连；SMB 根可读取 |
| `192.168.1.120` PVE2 Ubuntu | 可达 | 6/6；22 可连 |
| PVE1/PVE2/ESXi-A/ESXi-B 管理节点 | 可达 | 管理端口可连 |
| `10.10.10.128` Ubuntu、两组 iKuai/OpenWrt | 可达 | ICMP 与相应管理端口可连 |
| `192.168.1.110` 笔记本 | 无响应 | 4/4 丢失；可能关机、睡眠、换址或防火墙，不判为故障 |
| ESXi-C 宿主 | 未测试 | 资产表没有管理 IP |

两台候选机的 6379/6380/17890/17891/58600 均未从开发机开放。这是合适的默认安全姿态，也可能表示
服务尚未部署/启动；不能由此推断 QMT 是否登录。`198.51.100.113:18789` 是唯一可见的 OpenClaw 候选
端口，且明文 HTTP HEAD 返回 `200 OK`，必须优先完成安全审计和收口。

原始证据：`runtime_data/evidence/network/lan_connectivity_20260914_1146.json`。

## 后续实施顺序

1. **N0 双向网络验收**：在 125 和 113 各运行目标机探针，验证到 Coordinator、NAS、网关和 NTP 的
   反向连通；记录防火墙规则，不使用全端口开放。
2. **N1 主机基线**：两台 Win11 固定地址、禁止睡眠、自动恢复供电、NTP 对时；分配 `qmt-125` 与
   `qmt-113` 稳定 machine_id。
3. **N2 Coordinator VM**：PVE2 新建 1–2 vCPU、2 GB RAM、20 GB 系统盘 Ubuntu VM，部署
   Coordinator、Agent Gateway 和本地 SQLite WAL；每日向 NAS 复制审计，不从 NAS 运行。
4. **N3 Windows Host Agent**：先只上报 QMT/Redis/Bridge/账户/持仓/委托/成交/策略快照，不开放订单；
   Redis 与 QMT RPC 继续只监听本机。
5. **N4 Fleet Monitor Tray/Dashboard**：展示全部机器、两套账户的 `QUERY_PRIMARY`、
   `ACTIVE_EXECUTOR`、租约、快照时间、策略和异常；关闭 UI 不影响 Linux Coordinator 服务。
6. **N5 OpenClaw 只读工具**：保留现有 Agent 设置，各增加一个最小 BigQMT Query 工具和独立凭据；
   执行安全审计、DM pairing/allowlist 和命令来源限制。先完成手机查询。
7. **N6 模拟盘订单意图**：只给指定 Agent `qmt-executor-simulation` 角色，完成预览/确认、幂等、过期、
   重放、断网、双主冲突测试。主机暂定 125，113 始终只读。
8. **N7 人工接管演练**：停止 125，核对活动委托、成交、持仓与袖套后人工把模拟执行权切至 113；验证
   fencing token 能拒绝旧主机迟到订单。初版不做自动交易接管。
9. **N8 长期稳定性**：连续记录 Windows/WSL 重启、OpenClaw 中断、Coordinator/NAS 中断和 ESXi 重启；
   OpenClaw 或 NAS 故障不得中断本机 v1.1.15，Coordinator 故障必须阻止新增订单。
10. **N9 正式盘**：继续 `READ_ONLY`。未来正式下单另开授权、风险限额、Agent 身份和验收阶段。

本次只完成评估、只读网络探测和文档记录，没有启动远程服务、修改防火墙、改变 QMT/Bridge/Tray、
切换执行权或发送订单。
