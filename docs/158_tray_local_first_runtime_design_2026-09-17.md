# 托盘本地优先与独立运行设计

## 1. 目标

每个 Windows 主机上的 BigQMT 托盘必须是一个可以独立启动的本地程序。首次运行时完成本机配置，之后运行只读取本机缓存和本地 QMT/Redis/Bridge/Dashboard；不得因为 NAS、另一台 QMT 主机、OpenClaw 或另一只托盘不可达而无法启动。

Coordinator 是唯一允许的远程控制面依赖：它只负责执行资格、账户单执行主机仲裁、主机心跳和策略事实汇总。Coordinator 不可达时，托盘仍启动并继续本地监控，但必须自动进入 `READ_ONLY_COORDINATOR_OFFLINE`，禁止下单。

## 2. 依赖边界

| 组件 | 启动是否必需 | 运行期用途 | 不可达时的行为 |
|---|---:|---|---|
| 本机 Windows | 是 | 托盘进程和本地服务 | 托盘无法运行 |
| 本机 QMT/MiniQMT | 否（托盘仍可启动） | 账户、持仓、委托、行情和策略执行 | 显示 `QMT_DOWN`，可按本机策略尝试启动；执行锁定 |
| 本机 Redis/Bridge/Dashboard | 否（托盘仍可启动） | RPC、快照、看板和策略状态 | 分别显示故障；不影响托盘进程驻留 |
| Coordinator | 否（托盘仍可启动） | ACTIVE_EXECUTOR 仲裁、租约/授权、心跳和事实接收 | `READ_ONLY_COORDINATOR_OFFLINE`，禁止下单 |
| NAS | 否 | 首次导入、人工更新、备份/归档 | 完全不影响已初始化托盘 |
| 其他 Windows 主机/OpenClaw | 否 | 远程查询或人工控制 | 本机托盘仍可运行 |

## 3. 便携目录

每台机器只复制一个本地目录。示例：

```text
BigQMTTray_host-125\
  BigQMT_Simulation.exe
  BigQMT_Production.exe
  tray-runtime\
    src/                       # 打包运行时（EXE 可为 onedir）
    config/                    # 只读模板，不放真实值
  local/                       # 唯一本机可写区，迁移时随目录备份
    machine.local.json         # 路径、端口、账户和 Coordinator 地址
    host.json                  # host_id、软件版本、初始化时间
    secrets\
      simulation.key.dpapi    # Windows DPAPI 保护的模拟授权 Key
      production.key.dpapi    # Windows DPAPI 保护的正式授权 Key
      qmt-credentials.ref     # Windows Credential Manager 引用，不保存明文密码
      redis-credentials.ref   # 可选，本机 Redis 凭据引用
    state\                     # 本机快照、策略续接状态、outbox
    logs\                      # 托盘和本机服务日志
    backups\                   # 配置迁移前自动备份
```

EXE 默认从自身目录定位 `local/`。不再把 NAS 路径作为启动配置来源。若需要安装到 `Program Files`，则把 `local/` 改为 `%ProgramData%\\Kitling\\BigQMT\\<host-id>`，通过本机环境变量或启动参数指定；两种方式都不访问 NAS。

## 4. 首次运行流程

1. EXE 检查 `local/machine.local.json` 和 `local/host.json`。
2. 文件不存在时进入 `SETUP_REQUIRED`，显示本机初始化界面；不退出、不尝试访问 NAS。
3. 初始化界面配置：
   - 主机标识 `host_id`、本机 IP（默认自动探测，可人工修正）；
   - 模拟/正式 QMT 根目录与 `bin.x64`；
   - 模拟/正式账户号；
   - Redis host/port/db、Bridge 端口、Dashboard 端口；
   - Coordinator endpoint 和心跳周期；
   - 本机策略目录、策略开关和自动启动/自动恢复开关；
   - 对应账户的授权 Key 文件。
4. 程序验证本机 QMT 目录、端口格式和 Key 的账户/profile/有效期/签名；不接受把密码、Fact Secret、Redis 密码写入 JSON。
5. 授权 Key 通过 Windows DPAPI 加密后写入 `local/secrets/`；QMT 密码写入 Windows Credential Manager；原始文件不复制到 NAS、不写日志。
6. 所有检查通过后原子写入本地配置，并生成 `local/backups/<timestamp>/` 备份。
7. 首次启动默认仍为只读，直到 Coordinator 返回本机为该账户的合法执行主机；只有模拟盘在审批后可打开执行窗口，正式盘需单独授权。

## 5. 后续启动流程

```text
启动 EXE
  -> 只读 local/ 配置和本机密钥
  -> 启动/检查本地 QMT、MiniQMT、Redis、Bridge、Dashboard
  -> 本地健康状态显示
  -> 异步连接 Coordinator
       ├─ 可达且本机获准：显示 EXECUTOR_READY
       ├─ 可达但非本机：显示 READ_ONLY_NOT_EXECUTOR
       └─ 不可达：显示 READ_ONLY_COORDINATOR_OFFLINE
```

NAS 不在该流程中。NAS 更新必须由用户在托盘菜单中显式执行“导入新配置/备份本机配置”，或者运行一次 `bootstrap_private_config.py`；导入完成后仍使用本地副本。

## 6. 授权 Key 与账户隔离

- 模拟 Key 和正式 Key 分开保存、分开校验、分开撤销。
- Key 只代表“这台主机可以申请哪个账户的执行资格”，不代替 Coordinator 的单主机仲裁。
- 删除本机 Key 后，托盘可继续启动和只读监控，但永远不能成为执行主机。
- Coordinator 发现同一账户多个主机同时持有有效执行资格时，全部降级只读，直到冲突消除。
- 日志、诊断报告、Dashboard 和 OpenClaw 只显示 Key 指纹前 8 位、状态和过期时间，不显示原文。

## 7. NAS 离线与迁移验收

### NAS 离线验收

1. 完成一次首次初始化，确认 `local/` 已生成。
2. 断开 NAS 或移除 NAS 映射盘。
3. 启动两个托盘 EXE。
4. 预期：托盘图标出现，本地 QMT/Redis/Bridge 状态正常显示；不出现“配置文件找不到 NAS”的错误。
5. Coordinator 在线时仍可上报心跳；Coordinator 断开时只显示离线并锁定订单。

### 主机迁移验收

1. 停止旧机托盘，备份旧机 `local/`（不复制 QMT 的大行情数据库）。
2. 新机复制便携目录，首次运行重新确认 QMT 根目录和本机 IP。
3. 不复制旧机的明文凭据；授权 Key 重新导入并生成 DPAPI 文件。
4. Coordinator 观察旧机心跳过期后，再将新机提升为执行候选。
5. 验证策略续接快照、持仓归属、策略子账户累计收益和本地 outbox 去重键不重复。

## 8. 当前实现差距与后续任务

当前版本已经满足“运行期不读取 NAS”的核心规则，`load_machine_local()` 是本地唯一加载器，`bootstrap_private_config.py` 是显式导入工具。仍需完成：

1. 把托盘账户、端口和路径从源码默认值改为 `local/machine.local.json`；
2. 增加首次运行配置界面/初始化命令，并把 EXE 默认根目录切换到便携目录的 `local/`；
3. 增加 DPAPI/Windows Credential Manager 密钥适配层；
4. 将 NAS 导入、导出和备份做成托盘菜单的显式动作；
5. 增加“NAS 断开仍启动”的 Windows 集成测试和两台主机迁移验收脚本。

完成第 1～3 项后，托盘才算达到“独立文件、首次配置、运行期无 NAS 依赖”的正式版本。
