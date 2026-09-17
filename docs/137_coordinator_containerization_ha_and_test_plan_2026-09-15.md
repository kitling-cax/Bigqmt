# 137 Coordinator 容器化 / 高可用 / 测试 后续规划

日期：2026-09-15
范围：Coordinator 单权威 + 冷备切换 + 防双主安全 + 迁移容器化；含分层测试计划。本文是
规划落盘，不执行任何部署、编码、下单；作为后续执行依据，可由主线程后续并入
multi_host_program.yaml 的 HA 相关里程碑。
关联：docs/120、docs/122、docs/127、docs/136；scripts/coordinator/serve.py；
src/kitling_bigqmt/coordinator_core.py。

## 0. 现状基线（读码核对，2026-09-15）

### 已实现（可直接单测）

- SQLite WAL（PRAGMA journal_mode=WAL）
- 表：coordinator_meta(epoch)、hosts、account_leases(mode/fencing_token/
  coordinator_epoch/expires_at)、intents、audit_events
- epoch() / bump_epoch()：bump 时 BEGIN IMMEDIATE、epoch 自增、并把所有租约
  expires_at 置 0 作废
- grant_lease()：fencing_token 单调递增，每账户单行 UPSERT
- validate_lease()：校验 host_id / mode / token / epoch / 未过期，任一不符抛
  StaleLeaseError（fail-closed）
- preview_intent() / confirm_intent()：均先 validate_lease

### 缺失（防双主的关键缺口，M2 要补）

- 无 coordinator_instance_id：只有 epoch，无法识别"有第二台在跑"
- 无单实例启动锁（flock / 命名 mutex）：两个 serve.py 指向同一 SQLite 文件当前可
  同时起来，第二个能发更新的 token 抢租约，这是当前唯一真正的双主漏洞
- 执行机侧"instance_id/epoch/token 三件套"下单前强校验尚未接线

### serve.py 隔离钩子（测试隔离零成本）

- 环境变量：BIGQMT_COORDINATOR_BIND / BIGQMT_COORDINATOR_PORT /
  BIGQMT_COORDINATOR_DB / BIGQMT_PROJECT_ROOT
- 端点（以 M0 读码核对的最终清单为准）：GET /healthz 返回 readonly-foundation；
  只读 fleet / executor-preview / progress；POST /api/v1/hosts/heartbeat 只收只读心跳

## 1. 已定共识

- 低频交易下不上三节点多数派；采用"单权威 + 冷备 + 脚本化切换"
- fail-closed：续不上租约停手；bump_epoch 作废旧代际许可；冷备同一时刻只有一台写
- 容器化：serve.py 纯标准库，python:3.12-alpine 即可；铁律——状态落持久卷、严格
  单副本（不用 replicas>1 / 不做多副本快速重生）
- PVE 语境首选 LXC（快照/vzdump/pct 白送）；Docker 镜像定位为跨平台迁移产物
- VPS 是容器化最合适场景，推荐 Tailscale；公网裸跑必须先加 TLS + token 鉴权
- 状态 DB 必须落本地盘/卷，禁止放 SMB 共享路径

## 2. 待拍板阻塞项（未定则卡住）

1. 主方案：A（保留 .121 生产 + 并行打 Docker 迁移产物，推荐）或 B（直接切 PVE1
   专用 LXC）
2. 子网路由：10.10.10.x / 10.10.11.x 机器到 .121:18443 走哪台爱快/飞塔，需验证
   跨子网可达
3. 飞塔：放行 18443，还是只走 Tailscale
4. Coordinator 固定 IP：沿用 .121 还是改 .123

契约点（决定测试写法）：

- instance_id 稳定性：同机原地重启 instance_id 不变；failover 换主必须 epoch+1 且
  执行机只认 epoch 更大才接受新 id
- 下单时机：下单前是否强制"先续租成功才允许"，还是持未过期租约即可
- 阈值：租约 TTL（建议 30s）、容许最大 RTT（建议 2s）、failover RTO（建议 <=5s）

## 3. 执行路线图 M0-M8

| 里程碑 | 内容 | 主要产出 / 验证 |
|---|---|---|
| M0 | 代码基线核对（只读） | "已有/待补"差异表；定 fixture；搭隔离环境 |
| M1 | 容器化最小可用 | Dockerfile（python:3.12-alpine）+ 持久卷；healthz 200；重启 3 次账本不丢 |
| M2 | 防双主安全件（最高优先，先写测试再补码） | 单实例启动锁 + instance_id + 三件套校验；L1/L3/L4 全绿 |
| M3 | 冷备 + 脚本化切换 runbook | freeze→restore→bump_epoch→start→health；单写监视；L5/L6 全绿 |
| M4 | PVE LXC 生产形态 | 专用 Ubuntu 24.04 LXC；同 fixture 回归 |
| M5 | 迁移目标平台落地（按需） | Ubuntu/VPS/Windows/群晖/TrueNAS 矩阵 |
| M6 | 执行机接入 + 三件套接线 | 只读机永远 ORDER_GATED；持最新租约者才可下单 |
| M7 | 故障注入演练 | 双主拦截 / epoch 回退 / 断连 / 冷备切换 全部复演 |
| M8 | 文档 + NAS 发布（需授权） | 架构图、runbook、部署手册、故障记录、测试报告 |

推荐顺序：M0 → M2(1+2) → M1 → M3 → M4 → M6 → M7 → M8，M5 按迁移需要插入。理由：
容器化是"搬家能力"，防双主是"安全底线"，安全件与部署形态无关故先做。

## 4. 防双主安全机制（三层）

### (1) 单实例启动锁（必须，最硬）

- Linux：启动即对锁文件 flock(LOCK_EX | LOCK_NB)，抢不到则拒绝启动 + 日志 + 告警
- Windows：命名 mutex（CreateMutexW），已存在则拒绝启动
- Docker：入口脚本先 flock 再 serve；共享持久卷天然互斥
- 效果：第二台 Coordinator 物理上起不来，双主从根上消除

### (2) 执行机下单前三件套强校验（必须，便宜）

- 租约记录追加 coordinator_instance_id；签发带 instance_id + epoch + fencing_token
- 下单前四项全真才放行：instance_id==本地记忆权威ID；epoch==本地记忆 epoch；
  fencing_token 单调不减且==最近签发值；租约未过期
- 任一不符或过期 -> ORDER_GATED 只读停单（fail-closed，宁可空仓不可双杀）

### (3) 哨兵（可选，先不做）

- 托盘周期 GET /instance + /epoch 对比本地，疑似双 instance / epoch 回退 -> 只告警，
  不参与安全判定

## 5. 冷备 + failover runbook（五步，半自动，分钟级）

1. freeze 租约：通知现有执行机停单（ORDER_GATED / 租约冻结）
2. 恢复账本：从 .121 最新本地备份 + NAS 异地副本恢复到冷备
3. bump_epoch：全局 epoch+1，旧主已签发许可全部作废
4. 启动冷备：新主抢锁成功成为唯一权威
5. 健康检查：/healthz + /instance + 一次只读心跳确认后才放行执行机

核心价值：任何时刻只有一台在写，split-brain 概率为零；切换期间执行机自动 fail-closed。

## 6. 迁移目标平台矩阵

| 平台 | 可行性 | 定位 | 注意 |
|---|---|---|---|
| Ubuntu / VPS | 最佳 | 生产/异地兜底 | VPS 用 Tailscale；公网加 TLS+token |
| PVE LXC | 首选 | 内网生产 | 快照/备份/迁移最好使 |
| Windows | 能跑但非首选 | 兜底 | 命名 mutex 锁；SQLite 落本地盘 |
| 群晖 / TrueNAS | 可跑 Docker | 仅冷备或临时接管 | 8G NAS 不做锁权威；账本禁放 SMB |
| 爱快 / OpenWrt | 不推荐 | 排除 | 2G 内存、软路由定位 |

## 7. 测试计划（核心）

### 7.0 总原则

- 不碰生产：BIGQMT_COORDINATOR_DB（临时）+ BIGQMT_COORDINATOR_PORT（18444/18445）
  隔离；绝不对 .121:18443 或正式 DB 再起实例
- 不让测试触发真下单：用"假执行器"桩记录 ORDER_GRANTED / ORDER_GATED，不调 QMT；
  仅 90000001 做带真实路径的 PREVIEW 冒烟，不 confirm 真实订单
- 每个用例三要素：输入操作 → 期望结果 → 判据
- 核心不变量：任何操作序列后，同一 account 任一时刻至多一个"未过期且未作废"
  ACTIVE_EXECUTOR 租约（一票否决）

### 7.1 L1 单元测试（coordinator_core.py，纯逻辑，可 TDD 先行）

| ID | 用例 | 期望 | 判据 |
|---|---|---|---|
| U1 | initialize() 幂等 + WAL | WAL 生效、幂等 | journal_mode=wal，二次调用不报错 |
| U2 | 初始 epoch() | ==1 | 精确相等 |
| U3 | bump_epoch() | epoch+1 且所有 lease expires_at=0 | 逐行断言 + audit 事件 |
| U4 | grant_lease() token | 1,2,3…单调 | 每次 +1 不重复 |
| U5 | 同账户重复授权 | 单行 UPSERT 覆盖 | count=1 |
| U6 | validate_lease 正确租约 | 通过 | 不抛异常 |
| U7 | host/token/epoch 不匹配 | StaleLeaseError | 分别断言 |
| U8 | 过期租约 | StaleLeaseError | 详情 lease expired |
| U9 | 非 ACTIVE_EXECUTOR | StaleLeaseError | — |
| U10 | bump_epoch 后旧 Lease | 立即失效 | validate 抛错 |
| U11 | intent 非本租约/旧 token | StaleLeaseError | — |
| U12 | 不变量检查器 | 随机 grant/bump/expire 后至多 1 个有效租约 | 跑 N 次 |

注：U1-U11 大部分针对 coordinator_core 现状逻辑；U12 是命门测试，单独脚本反复轰炸。

### 7.2 L2 接口/集成（单实例，临时 DB + 端口）

| ID | 用例 | 期望 |
|---|---|---|
| I1 | GET /healthz | 200 + readonly-foundation |
| I2 | GET executor-preview | 只读，无写库副作用 |
| I3 | POST /api/v1/hosts/heartbeat | 合法只读 200；非法 400 |
| I4 | 重启后 current_lease | 持久化、token/epoch 不变 |
| I5 | 并发客户端 | 无崩溃、不变量成立 |

### 7.3 L3 防双主 fence（最高优先级，双进程 + 同一临时 DB）

| ID | 用例 | 期望 | 判据 |
|---|---|---|---|
| F1 | 先起 A 再起 B（同 DB） | B 拒绝启动 exit!=0，A 不受影响 | 退出码 + A healthz 仍 200 |
| F2 | B 强起后写租约 | B 无法 grant_lease | 没锁不 serve |
| F3 | A kill -9 | 锁自动释放 | 稍后 B 能拿锁启动 |
| F4 | 陈旧锁文件（含 PID） | 识别 stale → 接管（先 bump_epoch） | 日志 + epoch 已 +1 |
| F5 | Docker 同 volume 两容器 | 第二个 blocked | 第二实例启动失败 |
| F6 | Windows 命名互斥 | 同名第二进程拒绝启动 | exit!=0 |
| F7 | 跨平台一致性 | flock 与 mutex 等价 | 两平台同套用例全绿 |

关键判据：F1/F2/F5/F6 任一不通过，本项目不允许上线。

### 7.4 L4 执行机 fail-closed（假执行器桩，不碰 QMT）

| ID | 用例 | 期望 |
|---|---|---|
| C1 | 租约过期后下单 | ORDER_GATED，绝不 fail-open |
| C2 | token 旧/被 bump 作废 | ORDER_GATED |
| C3 | epoch 回退 | ORDER_GATED |
| C4 | 看到两个不同 instance_id（同 epoch） | ORDER_GATED + 告警 |
| C5 | 断网续不上租约 | 到期自动只读停单 |
| C6 | 下单恰在租约过期瞬间 | 确定性 gated，不半放行 |

### 7.5 L5 冷备 + failover 演练（端到端）

| ID | 步骤 | 期望/判据 |
|---|---|---|
| R1 | freeze 租约 | 旧主执行机收到 ORDER_GATED 进入只读 |
| R2 | 恢复到冷备 | token/epoch 与备份一致 |
| R3 | bump_epoch | 全局 epoch+1，旧许可全作废 |
| R4 | 启动冷备 | 抢锁成功唯一权威，healthz 200 |
| R5 | 健康检查后放行 | 执行机续租成功，token 严格大于旧值不复用 |

全程跑 writer 监视器：任一瞬只能有一个实例写 account_leases；记录 RTO（freeze 到
新权威可服务），目标 <=5s。

### 7.6 L6 账本 / 备份 / 损坏

| ID | 用例 | 期望 |
|---|---|---|
| P1 | 在线备份（WAL checkpoint + copy） | 恢复后 token/epoch 一致无丢失 |
| P2 | 损坏注入（截断/半写） | 检测到损坏拒绝 serve（fail-closed） |
| P3 | DB 放 SMB/网络共享路径 | 拒绝或明确告警 |
| P4 | 备份频率 + 保留数 | 可回退最近 N 个 |

### 7.7 L7 跨平台 / 容器 / 迁移

| ID | 用例 | 期望 |
|---|---|---|
| T1 | Docker 构建 + --rm 冒烟 | healthz 200 |
| T2 | 同一 fixture DB 到 Ubuntu/Docker/LXC | instance/epoch/租约一致 |
| T3 | 迁移（DB+config 拷新主机） | 起服务→healthz→租约流程通过 |
| T4 | 校验和/镜像 id 固化 | 发布产物可复核 |
| T5 | 群晖/TrueNAS 作冷备 | 只读可跑，绝不写账本 |

### 7.8 L8 网络 / 连通（阻塞项，先做）

| ID | 用例 | 期望 |
|---|---|---|
| N1 | 本机→.121:18443 TCP | 已通（现状验证） |
| N2 | 10.10.10.x/11.x 跨子网→.121:18443 | 待确认，不通则执行机接不上锁 |
| N3 | Tailscale 下执行机访问 | 通 + 本地解析正常 |
| N4 | 飞塔白名单 | 白名单通、非白名单被拒 |
| N5 | 延迟/丢包容忍 | 定义最大 RTT 阈值，超限判 unhealthy |

### 7.9 L9 非功能性 soak（低频，轻量）

连续 48h：无手动重启内存稳定、无脏重启、restart=unless-stopped 生效、并发突发心跳
不丢、时钟偏移下 fail-closed 仍正确（用 monotonic / 服务端权威时间判断过期）。

## 8. 验收门槛（Definition of Done）

以下必须全绿才算"可上线"，不是"能跑"：

1. U12 不变量轰炸通过（无序操作不出现双有效租约）
2. F1/F2/F5/F6 双主启动被拦死
3. C1-C6 无一 fail-open
4. R1-R5 全链路走通，全程单写，RTO<=5s
5. P1/P3 备份一致、SMB 被拒
6. N2 网络 / Tailscale 可达

## 9. 测试环境矩阵

| 环境 | 用途 | 隔离参数 |
|---|---|---|
| 本机 Windows（F 盘） | 单测、Windows mutex 分支、故障注入 | 临时 DB + 18444 |
| .121 Ubuntu | fence(flock)、failover、网络 | 临时 DB + 18444 |
| Docker（本机/WSL2） | 容器化 + 跨平台 fence | tmpfs/临时 volume |
| PVE LXC | 生产形态回归 | 同 .121 |
| VPS + Tailscale | 异地连通、延迟、TLS | 独立 DB |
| .125/.113 | 执行机接入 + fail-closed 消费端 | 只连测试端点 |

## 10. 测试自动化产物

建议 scripts/test/ 下（路径与命名后续以 M0 为准）：

- test_unit.sh（纯逻辑，任何机可跑）
- test_fencing.sh（双进程 + 临时 DB）
- test_failover.sh（起主/冷备 + 故障注入）
- run_all.sh（全量 + 汇总 exit code + md 报告）
- Dockerfile 加一层 docker run --rm <image> scripts/test/run_all.sh 以取代 CI，跨
  迁移目标一键回归

报告落 reports/test/（写到 NAS 需单独授权）。

## 11. 测试排期映射

| M | 测试动作 |
|---|---|
| M0 | 读码核对 + fixture + 隔离环境 |
| M1 | L7-T1 容器冒烟 |
| M2 | L1 全部 + L3 全部 + L4 全部（先写测试再补码） |
| M3 | L5 全部 + L6 全部 |
| M4/M5 | L7 T2-T5 |
| M6 | L4 接真执行机 + L8 |
| M7 | 整体故障注入复演 |
| M8 | 汇总报告 → NAS（需授权） |

## 12. 安全边界

- 本轮仅规划落盘；未部署、未编码、未下单、未改配置
- 模拟账户 90000001 后续验证也只能 PREVIEW，不得 confirm 真实订单（除非主线程单独
  授权）
- 正式账户 90000002 保持只读，不触碰任何交易路径
- 任何测试绝不连接 .121:18443 或正式 coordinator DB；隔离端口 + 临时 DB
