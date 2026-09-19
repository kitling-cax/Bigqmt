# `.125` Fact Secret 轮换与 `.121` Shadow 信任更新

## 现状

`.121` 的 Shadow `18666` 当前健康，但受保护的
`/etc/kitling-bigqmt-coordinator-shadow/fact-identities.json`
目前只信任 `.105`。因此 `.125` 使用新 Secret 投递时返回 400
`FactAuthenticationError` 是预期结果。

本项目使用 HMAC-SHA256。这里没有可单独分发的公钥；Coordinator 必须安全取得与 `.125` 完全相同的 `secret_b64`。Secret 不得经过 Git、NAS、聊天记录或普通报告。

## 推荐轮换方式

1. `.125` 运维人员在受保护目录确认新 Secret 文件和 key_id，**不输出文件内容**。
2. 通过受控 SSH/SCP 或其他 Secret 机制，把该文件安全送到 `.121` 的临时受保护路径，例如 `/run/kitling-bigqmt/host-125-new.json`。
3. `.121` 管理员在宿主机合并现有 `fact-identities.json`：保留 `.105` 条目，新增或替换 `host-125-fact-shadow-20260917` 条目；文件权限保持仅 Coordinator 容器用户可读。
4. 重启 Shadow 容器，不重启权威 `18443` 服务：

```bash
sudo docker compose -f /opt/kitling-bigqmt-coordinator/current/container/coordinator/compose.shadow.yaml up -d --force-recreate coordinator-shadow
sudo docker inspect --format '{{.State.Health.Status}}' kitling-bigqmt-coordinator-shadow
```

5. `.125` 再运行一次本机 `deliver_fact_outbox.py`，预期 `ACCEPTED` 或 `EMPTY`，pending 逐步降到 0。
6. 连续 ACK 观察一个完整周期后，再把旧 key 标记 `REVOKED` 并移除旧 Secret 文件。保留 key_id、host_id、轮换时间等审计元数据，不保留 Secret 内容。

## 不要做

- 不要把 HMAC Secret 当作“公钥”写入公开配置。
- 不要用 `.105` Secret 代替 `.125` Secret。
- 不要把 `.125` Secret 复制到项目树、NAS release、Git、OpenClaw 报告或聊天。
- 不要为解决 400 而把 `.125` 的 host_id 改回 `192.0.2.125`。

## 其他三项决策

1. `runtime_data/redis/production/` 先保留为隔离备份目录，不参与 6380 运行；确认新目录运行稳定并完成审计后再按本机备份流程归档。
2. 旧的 `invalid-192_0_2_125.json` 先隔离、撤销，待新 Secret ACK soak 完成后销毁；不得提交 Git。
3. 旧 `docs/154` 已标记为历史废弃；便携打包脚本现在强制要求传入真实 host_id 和 `:18666/api/v1/facts/ingest`，拒绝测试网占位地址。
4. 暂不加入“发现 Redis dir 漂移就自动 stop+start”。当前策略是启动前物化配置、端口不可达才补拉；先增加漂移告警和人工确认，避免托盘在交易时段误停 Redis。稳定验证后再单独评审自动修复。
