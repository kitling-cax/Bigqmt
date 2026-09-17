# `.121:18666` Coordinator Shadow C3/C4 部署记录

日期：2026-09-16 21:00（Asia/Shanghai）  
主机：`192.0.2.121`  
权威端点：`192.0.2.121:18443`（systemd，保持不变）  
影子端点：`192.0.2.121:18666`（Docker，SHADOW_READONLY）

## 构建

最小构建上下文从项目源树生成并上传到 `/tmp/kitling-bigqmt-coordinator-context-20260916-2047`，约 0.96 MB，不含运行数据库、凭据、授权 Key、NAS 挂载或 QMT/Redis 文件。

Docker Hub 在 `.121` 超时；使用可配置的 `PYTHON_BASE_IMAGE` 从 `docker.m.daocloud.io/library/python:3.12-slim` 拉取成功。

```text
image tag: kitling-bigqmt-coordinator:shadow-20260916
image id: sha256:709d7cd46b831099bacda47ca2dd19f01dec589acfb6917e9a925240a998721c
```

Dockerfile 已支持：

```text
--build-arg PYTHON_BASE_IMAGE=<registry>/library/python:3.12-slim
```

便于迁移到其他 Docker/OCI 主机。

## 数据准备

Shadow 数据库由 `/var/lib/kitling-bigqmt-coordinator/coordinator.sqlite3` 使用 SQLite `backup()` 在线备份生成：

```text
/var/lib/kitling-bigqmt-coordinator-shadow/coordinator.sqlite3
sha256=259020d448aa0c7f06911940239c8c6200b194ebc290e6486ec673aa7a726384
integrity_check=ok
inherited_leases_invalidated=0
```

Shadow 不共享权威库的 WAL、SHM、锁或 instance ID。

## 容器门禁结果

```text
container: kitling-bigqmt-coordinator-shadow
container_id: 4e636932d3b1587ef6e231c8c5217d2e0e66c99dc9d6db373709591ab4aeb65f
status: running / healthy
user: 10001:10001
readonly_rootfs: true
port: 192.0.2.121:18666 -> 18443/tcp
```

端点实测：

- `GET /readyz` → `200`, `mode=shadow_readonly`
- `GET /api/v1/hosts` → `200`, Shadow 独立库当前 `hosts=[]`
- `GET /api/v1/executor-preview` → `200`, 两账户均 `UNASSIGNED_READONLY`、无候选
- `GET /api/v1/progress` → `200`, `readonly=true`, `orders_enabled=false`
- `GET /api/v1/facts/ingest` → `404`
- `GET /api/v1/orders` → `404`
- `GET /api/v1/leases` → `404`

权威对照：`18443` 仍 `systemctl active`，`GET /api/v1/hosts` 仍返回 `.105` 的六项服务 UP 心跳；未被 Shadow 覆盖。

## 重启演练

已执行一次受控 `docker restart kitling-bigqmt-coordinator-shadow`：3 秒内端点重新返回 `ready`，约 15 秒后容器状态为 `running|healthy|RestartCount=0`；权威 `kitling-bigqmt-coordinator.service` 全程保持 `active`。

## 当前安全边界

- `orders_enabled=false`。
- 不创建 Token、Lease 或订单意图。
- 不启用 Host Fact ingest。
- 不访问 QMT、Redis 或券商接口。
- Shadow 仅用于容器运行、接口/数据隔离和故障演练；不能自动成为执行主节点。

## 后续

进入 24–48 小时 Shadow soak：记录健康、重启策略、端口隔离、数据库完整性和权威端点不变。Soak 通过后，才评估 LXC/其他 VM/TrueNAS/VPS 迁移；不自动切换 `18443`。
