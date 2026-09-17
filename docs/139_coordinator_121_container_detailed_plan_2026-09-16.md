# 139 Coordinator `.121:18666` 影子容器详细实施规划

日期：2026-09-16

状态：规划待确认；本文件不授权部署、端口开放、生产数据库修改或执行权限变更。

## 1. 目标拓扑

当前权威 Coordinator 保持不变：

```text
192.0.2.121:18443
└─ systemd: kitling-bigqmt-coordinator.service
   └─ /var/lib/kitling-bigqmt-coordinator/coordinator.sqlite3
```

新增独立影子容器：

```text
192.0.2.121:18666
└─ container: kitling-bigqmt-coordinator-shadow
   └─ /var/lib/kitling-bigqmt-coordinator-shadow/coordinator.sqlite3
```

两者不得共享 SQLite 文件、WAL、锁文件、instance ID、配置目录或日志目录。影子实例固定
`SHADOW_READONLY`，不得签发真实 lease、确认订单意图、触发 QMT/Redis 写入或改变
`18443` 的运行状态。

## 2. 本地项目目录规划

```text
C:\BigQMT\work\kitling_bigqmt\
├─ container\
│  └─ coordinator\
│     ├─ Dockerfile
│     ├─ compose.shadow.yaml
│     ├─ compose.production.yaml
│     ├─ entrypoint.sh
│     ├─ healthcheck.py
│     ├─ coordinator.env.example
│     ├─ logrotate.example.conf
│     └─ README.md
├─ config\
│  ├─ coordinator.example.json
│  ├─ coordinator.shadow.example.json
│  ├─ schemas\
│  │  ├─ executor_key.v1.schema.json
│  │  ├─ key_observation.v1.schema.json
│  │  ├─ order_event.v1.schema.json
│  │  ├─ trade_fill.v1.schema.json
│  │  ├─ strategy_runtime.v1.schema.json
│  │  ├─ strategy_nav.v1.schema.json
│  │  └─ checkpoint_manifest.v1.schema.json
│  └─ contracts\
│     ├─ node_heartbeat.v1.json
│     ├─ execution_lease.v1.json
│     ├─ order_intent.v1.json
│     └─ order_result.v1.json
├─ scripts\
│  ├─ coordinator\
│  │  ├─ serve.py
│  │  ├─ backup.py
│  │  ├─ restore.py
│  │  ├─ verify_database.py
│  │  └─ bump_epoch.py
│  └─ container\
│     ├─ build_coordinator_image.ps1
│     ├─ package_coordinator_image.ps1
│     ├─ deploy_shadow_121.ps1
│     ├─ verify_shadow_121.ps1
│     ├─ promote_121.ps1
│     └─ rollback_121.ps1
├─ src\kitling_bigqmt\
│  ├─ coordinator_core.py
│  ├─ coordinator_instance.py
│  ├─ coordinator_key_authority.py
│  ├─ coordinator_event_store.py
│  ├─ coordinator_checkpoint_index.py
│  ├─ coordinator_archive.py
│  ├─ coordinator_outbox.py
│  └─ coordinator_health.py
├─ tests\
│  ├─ test_coordinator_instance.py
│  ├─ test_coordinator_key_authority.py
│  ├─ test_coordinator_event_store.py
│  ├─ test_coordinator_outbox.py
│  ├─ test_coordinator_container_lock.py
│  ├─ test_coordinator_backup_restore.py
│  └─ test_coordinator_shadow_mode.py
└─ dist\
   └─ coordinator-container\
      └─ <version>\
         ├─ image.tar
         ├─ image.sha256
         ├─ compose.shadow.yaml
         ├─ compose.production.yaml
         ├─ coordinator.example.json
         ├─ manifest.json
         ├─ checksums.sha256
         └─ README.md
```

`config/authorization` 下的模拟和正式 Key 是 Windows 主机本地文件，不进入容器镜像或
普通 NAS release。

## 3. `.121` 宿主机目录规划

```text
/opt/bigqmt-coordinator/
├─ releases/
│  └─ <version>/
│     ├─ compose.shadow.yaml
│     ├─ compose.production.yaml
│     ├─ manifest.json
│     └─ checksums.sha256
├─ current -> releases/<version>/
└─ images/
   └─ kitling-bigqmt-coordinator-<version>.tar

/etc/kitling-bigqmt-coordinator/
├─ coordinator.json
├─ trusted_key_issuers.json
├─ revoked_keys.json
└─ tls/

/etc/kitling-bigqmt-coordinator-shadow/
├─ coordinator.json
├─ trusted_key_issuers.json
└─ shadow-policy.json

/var/lib/kitling-bigqmt-coordinator/
├─ coordinator.sqlite3
├─ coordinator.sqlite3-wal
├─ coordinator.sqlite3-shm
├─ coordinator.lock
├─ coordinator_instance_id
├─ epoch_floor
└─ backups/

/var/lib/kitling-bigqmt-coordinator-shadow/
├─ coordinator.sqlite3
├─ coordinator.sqlite3-wal
├─ coordinator.sqlite3-shm
├─ coordinator.lock
├─ coordinator_instance_id
├─ source_backup_manifest.json
└─ backups/

/var/log/kitling-bigqmt-coordinator/
/var/log/kitling-bigqmt-coordinator-shadow/
/var/spool/kitling-bigqmt-coordinator-nas/
```

正式状态卷与影子状态卷必须是两个明确的 bind mount，不使用匿名 Docker volume，以便
备份、审核和未来迁移。

## 4. 容器运行参数

影子 Compose 固定要求：

```text
container_name: kitling-bigqmt-coordinator-shadow
host port: 192.0.2.121:18666
container port: 18443
mode: SHADOW_READONLY
restart: unless-stopped
replicas: 1
root filesystem: read-only
runtime user: non-root fixed UID/GID
state volume: /var/lib/kitling-bigqmt-coordinator-shadow
config volume: /etc/kitling-bigqmt-coordinator-shadow:ro
/tmp: tmpfs
```

安全开关：

```text
BIGQMT_COORDINATOR_MODE=SHADOW_READONLY
BIGQMT_EXECUTION_WRITES_DISABLED=1
BIGQMT_LEASE_GRANTS_DISABLED=1
BIGQMT_INTENT_CONFIRM_DISABLED=1
BIGQMT_COORDINATOR_PORT=18443
```

影子响应均携带 `mode=SHADOW_READONLY` 和 `orders_enabled=false`。所有写执行权限的接口
必须返回拒绝，不允许仅靠前端隐藏。

## 5. 数据库规划

现有表继续保留：

```text
coordinator_meta
hosts
account_leases
intents
audit_events
```

新增表：

```text
coordinator_instances
key_observations
revoked_keys
account_authority_state
order_events
trade_fills
strategy_runtime_events
strategy_nav_snapshots
checkpoint_index
archive_jobs
alerts
```

迁移脚本必须幂等、带 schema version，并能在数据库副本上先升级验证。不得直接用生产
`18443` 数据库试跑 schema migration。

## 6. 单实例与 epoch

启动入口先对状态目录中的 `coordinator.lock` 执行 `flock(LOCK_EX | LOCK_NB)`。拿不到
锁时容器退出非零；不得继续启动 HTTP。

授权返回必须包含：

```text
coordinator_instance_id
coordinator_epoch
fencing_token
lease_expires_at
```

`epoch_floor` 独立保留最高 epoch。恢复旧数据库时使用：

```text
new_epoch = max(database_epoch, epoch_floor) + 1
```

避免恢复旧备份后 epoch 回退导致旧 token 重新有效。

## 7. 影子数据库生成

不能直接复制运行中的 SQLite/WAL 文件。步骤固定为：

1. 对当前权威数据库执行 SQLite online backup；
2. 为备份生成 SHA-256 与 manifest；
3. 将备份复制到 shadow 状态目录；
4. 在副本中失效全部 lease；
5. 分配新的 shadow instance ID；
6. 执行 schema migration；
7. 运行 integrity check；
8. 才允许容器启动。

影子数据库发生的 heartbeat、假 Key 冲突和测试订单事件只存在于副本中。

## 8. 影子数据来源

影子阶段分三类输入：

1. 生产数据库一致性副本：验证迁移兼容；
2. 本地 fixture/fake hosts：测试双 Key、租约、断链和恢复；
3. 只读遥测镜像：Host Agent 可选将心跳与订单事件副本上报 `18666`，但影子 ACK 不参与
   下单判定。

真实执行仍只认 `18443`。任何客户端不得把 `18666` 返回的 lease 用于下单。

## 9. NAS 目录规划

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\
├─ releases\coordinator\
│  ├─ candidate\<version>\
│  └─ stable\<version>\
├─ backups\coordinator\
│  ├─ production\<backup_id>\
│  └─ shadow\<backup_id>\
├─ archives\coordinator\<YYYYMMDD>\
├─ checkpoints\<account_id>\<strategy_id>\<checkpoint_id>\
└─ reports\coordinator\
   ├─ build\
   ├─ shadow_acceptance\
   ├─ migration\
   └─ incidents\
```

NAS 不保存运行中的 SQLite WAL，不承担实时锁，不直接运行 candidate release。容器镜像和
配置先复制到 `.121` 本地并验证哈希，再启动。

## 10. 网络规划

```text
18443: 当前权威 Coordinator
18666: 影子容器
```

影子端口初期只允许：

```text
192.0.2.105  开发主机
192.0.2.121  本机健康检查
```

`.125`、`.113` 后续做只读遥测验证时再加入白名单。影子端口不暴露公网，不配置
Cloudflare Tunnel/Funnel，也不作为手机下单入口。

## 11. 开发和部署阶段

### C0 契约冻结

完成 Key、Key observation、order event、trade fill、strategy runtime、NAV、checkpoint
schema；明确 event ID、幂等键、时间字段和 hash 规则。

### C1 安全核心

实现 instance ID、flock、epoch floor、fencing 校验、双 Key 锁定与 fail-closed 测试。

### C2 数据上报

实现 Windows 本地 Outbox、Coordinator 批量 ingest、事件去重、订单/成交归属、策略 NAV
和 checkpoint 索引。先在本地 fixture 测试，不连接真实订单通道。

### C3 容器产物

构建 linux/amd64 OCI 镜像、Compose、entrypoint、healthcheck、备份恢复和 manifest。

### C4 本地隔离测试

使用临时端口和临时 DB 完成单元、接口、双实例、恢复、损坏、NAS 断开与重启测试。

### C5 `.121:18666` 影子部署

上传已验证 release；创建 shadow 目录；恢复数据库副本；仅开放 `.105`；启动容器；执行
健康检查和测试心跳。

### C6 24 至 48 小时 soak

验证进程、内存、日志轮转、重启、数据增长、心跳新鲜度、NAS 积压和 Coordinator
不可达时的只读行为。

### C7 原地切换准备

只生成切换 runbook、最终备份和回退包，不自动切换 `18443`。切换需后续单独确认。

## 12. 影子验收门禁

必须全部通过：

1. `/healthz`、`/readyz`、`/api/v1/instance` 连续正常；
2. 容器重启三次，影子数据不丢；
3. 同一状态卷启动第二容器必定失败；
4. 数据库截断或 schema 不匹配时拒绝 ready；
5. 所有 lease/confirm/order-write 接口在 shadow 模式拒绝；
6. 两台假主机持有同账户 Key 时进入全局只读；
7. 删除一台假主机 Key 后按冲突解除规则恢复唯一候选；
8. Coordinator 断连后 Windows 托盘在 lease 到期时只读；
9. Outbox 断网积压、恢复补传且无重复事件；
10. NAS 断开不影响 Coordinator 仲裁；
11. 数据库一致性备份和恢复哈希一致；
12. 当前 `18443` systemd 服务全过程不受影响；
13. 生成完整 shadow acceptance 报告并归档 NAS。

## 13. 后续平台评估

影子容器和原地生产容器完成后，才比较 PVE LXC、其他 Ubuntu VM、TrueNAS 容器和 VPS。
评估使用同一镜像、同一 fixture、同一恢复包和同一验收脚本，避免为目标平台重新改代码。

