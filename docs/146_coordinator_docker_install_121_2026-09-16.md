# `.121` Coordinator Docker 运行时安装记录

日期：2026-09-16 20:47（Asia/Shanghai）  
主机：`192.0.2.121`（Ubuntu 24.04）  
目的：为 `.121:18666` Shadow Coordinator 准备可迁移的 OCI/Docker 运行时。

## 已执行

在用户明确授权“安装 Docker”后，通过 SSH 安装 Ubuntu 软件包：

```text
docker.io
docker-compose-v2
```

未修改现有 `kitling-bigqmt-coordinator.service`，未触碰权威 `192.0.2.121:18443`，未启动 Shadow 容器，未启用事实写入或任何下单/租约路由。

## 验证结果

```text
Docker version 29.1.3, build 29.1.3-0ubuntu3~24.04.2
Docker Compose version 2.40.3+ds1-0ubuntu1~24.04.1
systemctl is-active docker -> active
docker info (sudo) -> ServerVersion 29.1.3, Containers 0, Images 0
```

安装主机用户 `kitling` 当前未加入 `docker` 用户组；后续运维命令继续通过受控 `sudo` 执行，避免扩大 Docker socket 权限。是否加入用户组需单独评估，不作为本次安装的隐含动作。

## 当前边界

- 权威 Coordinator 仍为 `18443` systemd 服务。
- 影子端口 `18666` 尚未监听。
- `orders_enabled=false`；正式账户仍只读。
- Host Fact ingest、租约、订单和 QMT/Redis 写入均未启用。

## 下一步（单独批准后执行）

1. 构造最小 Docker build context，上传 `.121` 临时目录。
2. 使用 SQLite `backup()` 在线备份准备独立 Shadow 数据库，不复制运行中的 `-wal/-shm`。
3. `docker build`、`docker compose config` 和容器只读健康检查。
4. 仅启动 `18666` Shadow，执行 C3/C4 门禁与 24–48 小时 soak；期间不切换 `18443`。

