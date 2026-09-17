# 140 · Coordinator Shadow Container C0/C1 本地实现记录

日期：2026-09-16 19:09 +08:00  
状态：本地实现与测试通过；未部署到 `.121`；不改变当前 `18443`。

## 本次范围

完成 `.121:18666` 影子容器计划的 C0 契约冻结、C1 安全核心和 C3 容器基础产物的本地实现。
本次没有建立授权 Key、没有读取 Key 明文、没有申请/授予 Lease、没有写入 QMT/Redis、没有发送订单，也没有 SSH 或重启 `.121`。

## 已实现

| 组件 | 位置 | 约束 |
| --- | --- | --- |
| 单实例身份与锁 | `src/kitling_bigqmt/coordinator_instance.py` | 本地状态目录锁；稳定 UUID；`epoch_floor` 单调递增；实例不匹配或旧 epoch 失败关闭。 |
| Key 冲突仲裁纯函数 | `src/kitling_bigqmt/coordinator_key_authority.py` | 仅处理 SHA-256 指纹观察；两个主机同账户有效 Key 即 `DUPLICATE_KEY_LOCKDOWN`。 |
| C0 合同 | `config/schemas/*.v1.schema.json` | Key/观察、order event、fill、strategy runtime、NAV、checkpoint 的版本化字段。 |
| 影子 OCI 镜像 | `container/coordinator/Dockerfile` | Python 3.12、固定非 root UID 10001、没有 QMT/Redis/券商依赖。 |
| Shadow Compose | `container/coordinator/compose.shadow.yaml` | 仅 `192.0.2.121:18666:18443`；独立 shadow state/config bind mount；只读根文件系统、tmpfs、能力清空。 |
| 入口硬门禁 | `container/coordinator/entrypoint.sh` | 必须是 `SHADOW_READONLY` 且 `EXECUTION_WRITES/LEASE_GRANTS/INTENT_CONFIRM` 三开关均为 `1`（disabled），否则退出。 |
| 服务入口 | `scripts/coordinator/serve.py` | 进程启动时取得单实例锁并公布只读 instance identity；未新增订单、确认或租约 HTTP 写接口。 |
| 在线备份与影子准备 | `src/kitling_bigqmt/coordinator_backup.py` | 使用 SQLite backup API 生成一致副本、校验 SHA-256/`integrity_check`，并在 shadow 副本中使全部继承 Lease 立即到期。 |

## Key 状态规则

同一账户以 `account_id + environment` 隔离；模拟与正式 Key 不能互用。Coordinator 后续只保存观察元数据：`host_id`、Key 指纹、观察/到期时间、有效标志，不保存 Key 内容。

| 条件 | Coordinator 状态 | 订单能力 |
| --- | --- | --- |
| 无有效 Key 或 Key 到期 | `NO_VALID_KEY_READONLY` | 关闭 |
| 一个主机有效 Key、策略政策未开 | `SINGLE_KEY_POLICY_READONLY` | 关闭 |
| 一个模拟主机有效 Key、未来策略政策开 | `SINGLE_KEY_LEASE_ELIGIBLE` | 仍关闭；仅代表未来 Lease 候选 |
| 两个以上主机有效 Key | `DUPLICATE_KEY_LOCKDOWN` | 关闭，所有主机只读 |

即便 `SINGLE_KEY_LEASE_ELIGIBLE`，仍必须通过未来的 Coordinator Lease、fencing、Host Agent、本机策略与 QMT 二次检查；它不是下单授权。

## 容器边界

影子容器将使用 `/var/lib/kitling-bigqmt-coordinator-shadow`，绝不共享：

- `18443` 的 SQLite、WAL、SHM、锁、instance ID 或配置；
- NAS 的实时文件系统、锁或数据库；
- QMT/Redis/桥接的写入入口。

生产 Compose 文件仅是故意不可运行的未来模板。任何 `18443` 容器切换要等影子 24–48 小时验收，并取得单独确认。

## 验证

```text
py -3.12 -m pytest -q
247 passed in 18.45s
```

其中 Coordinator C0/C1/容器/在线备份定向回归 21 项通过，JSON schema 9 个文件均可解析。`pytest.ini` 增加 `testpaths = tests`，不再递归收集 `runtime_data/_pyinstaller_env` 的第三方测试，消除了其与另一个 PyInstaller 临时环境同名模块冲突。

## 下一步

1. C2：实现 Windows 本地 Outbox 与 Coordinator 去重 ingest，仅保存订单/成交/策略运行/NAV/checkpoint 事实，不创建订单写接口。
2. C3/C4：在有 Docker 的 `.121` 或构建机上构建 OCI image，临时 DB + 临时端口的隔离验证；SQLite online backup/restore/hash 工具已具备。
3. C5：仅在用户确认后部署 `.121:18666` shadow，先由 SQLite online backup 生成副本，并保持 `18443` 权威 systemd 服务不变。
