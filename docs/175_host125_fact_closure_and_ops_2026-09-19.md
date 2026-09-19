# `.125` Fact 闭环与后续运维记录

## 已完成

- `.125` 分支已推送到 `25293bf`，包含确定性 `*.sha256` 换行规则。
- `.121` Shadow 已 ACTIVE 信任 `.105` 与 `.125` 的 Fact identity。
- simulation：两轮 `ACCEPTED` 后 pending=0，后续为 `EMPTY`。
- production_readonly：两轮 `ACCEPTED` 后 pending=0，后续为 `EMPTY`。
- `orders_enabled=false`、`facts_only=true` 持续成立。
- `.125` 旧占位 Secret 已删除；Redis 6379/6380 目录正确；两个 Bridge Ping 已通过。

## 本次脚本修复

旧版 `enroll_shadow_fact_secret.ps1` 将 `.121` 脚本安装为 root 700，却以普通用户执行，可能出现 `Permission denied`。新版改为：

```text
sudo bash /home/kitling/bin/bigqmt-enroll-fact-host.sh <staged-file>
```

`.125`、`.113` 重新拉取对应分支后，未来主机均使用新版流程。

## `.121` 凭据运维

本项目不会在脚本、Git、NAS 或报告中保存 `.121` 密码。由于旧密码曾用于人工运维，建议由 `.121` 管理员在维护窗口完成：

1. 修改 `kitling` 登录密码；
2. 从指定运维端生成独立 ED25519 SSH 密钥；
3. 只把公钥加入 `.121` 的 `~kitling/.ssh/authorized_keys`；
4. 验证 SSH 公钥登录后，再撤销旧密码登录或保留受控备用入口。

该变更需要管理员明确执行，不能由本项目自动修改。SSH 公钥登录只用于 Coordinator 运维，不改变 Fact、策略或下单权限。

## 保留待办

- 托盘 Redis 目录漂移自愈：单独 Sprint，交易时段禁止自动 stop/start。
- 复盘 `192.0.2.125` 占位 host_id 的初始来源。
- `runtime_data/redis/production/` 作为隔离备份目录处理，不直接删除。
