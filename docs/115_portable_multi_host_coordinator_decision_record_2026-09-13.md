# P19/P21 可迁移配置与多主机协调决策记录

日期：2026-09-13  
状态：`DESIGN_RECORDED / COORDINATOR_HOST_PENDING_SELECTION / NO_RUNTIME_CHANGE`

## 已确认事项

1. 本开发机目录不变：
   - BigQMT：`C:\BigQMT\work\kitling_bigqmt`
   - 模拟 QMT：`C:\BigQMT\work\国金QMT交易端模拟`
   - 正式 QMT：`C:\BigQMT\work\国金证券QMT交易端`
2. 其他 Windows 运行机默认目录：
   - BigQMT：`E:\kitling_bigqmt`
   - 模拟 QMT：`E:\国金QMT交易端模拟`
   - 正式 QMT：`E:\国金证券QMT交易端`
3. `config/machine.local.json` 将成为每台机器唯一的路径、端口和协调端点覆盖文件。NAS 发布包和
   更新器必须保留该文件，不得把开发机 F 盘配置覆盖到目标机。
4. NAS `\\192.0.2.236\truenas\kitling_bigqmt\` 是只读代码更新源、备份和审计副本位置；目标机
   必须先复制到本地再运行，不从 SMB 共享目录直接运行策略或活动数据库。
5. 用户已观察到同一账户可在两台 QMT 电脑同时登录。系统允许两套 QMT、Tray 和 Bridge 在线，
   但同一账户只能有一台 `ACTIVE_EXECUTOR`，另一台必须为 `STANDBY_READONLY`。
6. 模拟账户 `90000001` 与正式账户 `90000002` 分别选主。正式账户当前仍处于 `READ_ONLY`；未来
   `SHADOW/LIVE` 是独立授权阶段，不能由迁移配置或主机租约自动开启。

## Coordinator 决策边界

Coordinator 负责机器登记、心跳、账户唯一执行租约、递增 fencing token、冲突检测和主备接管审计；
不保存券商/QMT 密码、不生成策略信号、不调用券商下单接口。Coordinator 不可达时两台机器都必须
停止新增订单，已有委托只做查询和对账。

NAS 心跳 JSON 可作为人类可读状态副本，但 SMB 文件锁不得作为订单安全仲裁。Tailscale 与
Cloudflare Tunnel 只作为连接和访问控制层。Cloudflare 原生仲裁只有 Workers + Durable Objects
路线具备候选资格；Workers KV 因最终一致性不得承担唯一执行锁。

Coordinator 最终宿主尚未确定：

| 候选 | 当前判断 |
|---|---|
| 独立低功耗 Ubuntu 小主机 + UPS | 故障隔离最佳，长期首选候选 |
| ESXi Ubuntu VM | 当前环境下性价比最高；两台 QMT 同址时优先候选 |
| 国内云 VPS | 两台 QMT 异地时优先候选；需验证公网稳定性 |
| Cloudflare Durable Objects | 技术可行；国内链路和额度需长时间验证 |
| ESXi OpenWrt | 保留路由/Tailscale 职责，不优先承载协调器 |
| Windows WSL Ubuntu | 可作过渡；需要 Windows 原生启动与看护服务 |
| TrueNAS SCALE App | 可运行；与存储升级和维护存在故障耦合 |

在用户选择前，不把任何候选写成既定生产依赖，不启动 Coordinator，也不改变当前单机策略运行状态。

## P19 M1 必须完成

1. 严格定义 `machine.local.json` schema，并输出脱敏 effective-config 与配置哈希。
2. 将 BigQMT/QMT/运行数据/日志/备份/Redis/staging/数据湖及协调端点收口到单文件覆盖；可推导目录
   使用相对路径。
3. 清理原生 Tray、PowerShell、Bridge 构建器、部署 profile、数据湖与健康检查中的生产硬编码路径。
4. 配置存在但损坏、端口冲突或路径越界时失败关闭，不得静默回退开发机 F 盘。
5. 保留一个生产调度器；旧 PowerShell Tray 不得与原生 EXE 同时调度模拟策略。
6. Coordinator 接口先抽象为可替换 URL，不绑定 ESXi、VPS、Cloudflare或其他具体宿主。

## 后续多主机验收

- 两台 Tray 同时启动时，同一账户最多一个 `ACTIVE_EXECUTOR`。
- 备用机可以查询和展示策略影子结果，但订单、撤单、补单和自动策略恢复全部拒绝。
- 主机失联、租约到期、Coordinator 重启或网络分区后，不存在两台机器同时接受订单的窗口。
- 初版仅允许人工接管；接管前完成活动委托、成交、持仓和策略账本对账。
- 软件升级、回滚、账户或路径变化后，正式账户自动回到 `READ_ONLY`。

本记录仅冻结设计决定。本轮未修改 QMT、Redis、Tray、Bridge、策略开关、账户或订单状态。
