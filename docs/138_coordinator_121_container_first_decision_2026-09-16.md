# 138 Coordinator 先在 192.0.2.121 完成容器开发的决策

日期：2026-09-16

## 决策

Coordinator 下一阶段先在当前 PVE 下的 Ubuntu 主机 `192.0.2.121` 完成 OCI/Docker
容器开发、影子验证和原地切换能力。当前阶段不同时迁移到 PVE LXC、其他虚拟机或
TrueNAS 容器，也不改变 Windows 托盘使用的稳定入口 `192.0.2.121:18443`。

最终运行平台暂不锁定。容器产物通过验收后，再单独比较：

- PVE 非特权 LXC；
- 其他 Ubuntu 虚拟机上的 Docker/Podman；
- TrueNAS 本机容器；
- 外网 VPS + Tailscale。

## 边界

- 容器镜像只包含代码和运行时，不包含 SQLite 状态、授权 Key、签名私钥或机器路径。
- Coordinator SQLite WAL 必须落在 `.121` 本地持久卷，禁止放到 SMB/NAS 路径。
- NAS 只保存一致性备份、不可变日志、报告、策略 checkpoint 和容器发布物。
- 容器严格单副本；不得通过 replicas、Swarm 或 Kubernetes 启动多个写实例。
- 当前 systemd 服务继续作为 `18443` 权威实例；开发容器先使用 `18666` 和复制数据库。
- 影子容器不得签发真实执行 lease，不得接收真实订单确认，不得触发 QMT/Redis 写入。

## 开发顺序

1. 补齐 `coordinator_instance_id`、启动锁和 epoch/fencing 三件套校验。
2. 完成 Key 观察、同账户多 Key 冲突锁定、吊销与恢复状态机。
3. 增加订单事件、成交事实、策略状态、NAV 和 checkpoint 元数据接口。
4. 增加本地 Outbox 去重与补传契约。
5. 生成 Dockerfile、entrypoint、compose、healthcheck、备份和恢复工具。
6. 在 `.121:18666` 用数据库副本运行影子容器，完成重启、损坏、双实例和 NAS 断开测试。
7. 通过 24 至 48 小时 soak 后，安排维护窗口原地切换到 `.121:18443`。
8. 容器稳定后再评估迁往 LXC、其他 VM、TrueNAS 或 VPS；平台迁移独立验收。

## 原地切换门禁

- 两个容器指向同一状态卷时，第二个必须因启动锁失败退出。
- 容器重启三次后 hosts、key observations、epoch、lease 和审计记录不丢失。
- 数据库损坏时 `/readyz` 失败且服务拒绝签发 lease。
- systemd 与容器不得同时绑定 `18443`。
- 切换前冻结所有 lease，切换后 `epoch + 1`，旧 token 全部失效。
- Windows 托盘在 Coordinator 不可达或 lease 过期时自动只读。
- 回退同样执行 `epoch + 1`，禁止恢复使用旧权限。

## 可移植产物

容器阶段完成后应形成一个平台无关发布包：

```text
coordinator-container-<version>/
├─ image.tar
├─ image.sha256
├─ compose.yaml
├─ coordinator.example.json
├─ env.example
├─ backup.sh
├─ restore.sh
├─ migrate-in.sh
├─ migrate-out.sh
├─ healthcheck.sh
├─ manifest.json
└─ README.md
```

发布包写入 NAS stable/candidate 通道，但运行时必须复制到目标机本地后启动。

## TrueNAS 后续评估原则

如果未来 Coordinator 运行在 TrueNAS 本机容器中，SQLite 可以使用 TrueNAS 本机的
专用 ZFS dataset 持久卷；仍禁止通过 SMB 网络共享访问 SQLite。需要独立验证容器
升级、dataset 快照、单实例锁、网络重启和 TrueNAS Apps 生命周期不会产生双主。
