# 144 · `.121` Shadow 容器运行时预检

日期：2026-09-16  
目标：`192.0.2.121:18666` 影子 Coordinator

## 只读预检结果

通过 SSH（用户 `kitling`）检查：

- SSH 可达；
- 当前 `kitling-bigqmt-coordinator.service` 为 `active`；
- 根/var 所在磁盘约 105 GB 可用；
- Docker、Podman、nerdctl、Buildah、containerd 均未安装或未运行。

## 影响

本地 Shadow Dockerfile、Compose、实例锁、Key 仲裁、在线备份、Outbox 和认证事实接收代码均已完成测试，但目前无法在 `.121` 构建 OCI 镜像或启动 `.121:18666`。当前 `18443` 权威服务和两个 Windows 托盘不受影响。

## 待确认的主机变更

需要在 `.121` 安装一个 OCI 运行时（建议 Docker Engine + Compose plugin，或用户指定 Podman 方案）。安装会改变 Ubuntu 主机软件包、可能启用后台 daemon，并需要 sudo 权限；因此本轮没有执行安装。

安装完成后顺序固定为：构建镜像 → 校验 manifest → SQLite online backup 生成 shadow 副本 → 启动 `.121:18666` → 13 项影子门禁 → 24–48 小时 soak。不得直接切换 `18443`。
