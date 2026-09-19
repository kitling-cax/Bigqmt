# `.125` / `.113` Fact Secret 注册到 `.121` Shadow

## 已确认状态

`.121:18666` Shadow Coordinator 处于 healthy 状态，facts ingest 已开启；当前信任文件仅包含 `.105` 的 `host-105-fact-shadow-20260917`。因此 `.125` 的 `FactAuthenticationError` 与 `.113` 的 `fact_secret_missing` 都不会自行恢复。

本流程只接通 Host Agent 的运行事实回传。它不授予策略下单、账户执行或租约权限，所有 payload 继续为 `orders_enabled=false`。

## 操作原则

- HMAC Secret 不经过 `.105`、NAS、Git、聊天、邮件或报告；
- `.125` / `.113` 各自使用本机生成的专属 Secret；
- Secret 从执行主机通过 SCP 直传 `.121`，在那里完成受保护信任文件合并；
- 脚本只输出 `host_id` 与 `key_id`，从不输出 `secret_b64`；
- `.121` 成功合并后会删除暂存副本，原机 Secret 保留在 `C:\ProgramData\Kitling\BigQMT\host-facts\`。

## `.125` 执行

在 `.125` 的项目根目录执行：

```powershell
Set-Location E:\kitling_QMT_work\kitling_bigqmt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\coordinator\enroll_shadow_fact_secret.ps1 `
  -SecretFile 'C:\ProgramData\Kitling\BigQMT\host-facts\host-125-fact-shadow-20260917.json'
```

成功后，运行两个 profile 的 facts-only 回归：

```powershell
py -3.12 scripts\host_agent\deliver_fact_outbox.py `
  --profile simulation `
  --secret-file 'C:\ProgramData\Kitling\BigQMT\host-facts\host-125-fact-shadow-20260917.json' `
  --outbox-path 'E:\kitling_QMT_work\kitling_bigqmt\runtime_data\state\simulation\host_agent_outbox.sqlite3' `
  --expected-host-id 192.168.1.125 `
  --endpoint http://192.168.1.121:18666/api/v1/facts/ingest
```

将 `--profile simulation` 和相关路径替换为 `production_readonly` 后再执行一次。期望结果为 `ACCEPTED` 或 `EMPTY`，pending 逐步归零。

## `.113` 执行

`.113` 先签发专属 Secret，不能复用 `.125` 文件：

```powershell
Set-Location E:\kitling_QMT_work\kitling_bigqmt
py -3.12 scripts\coordinator\manage_fact_identity.py `
  --host-id 10.10.10.113 `
  --key-id host-113-fact-shadow-20260917 `
  --output 'C:\ProgramData\Kitling\BigQMT\host-facts\host-113-fact-shadow-20260917.json'

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\coordinator\enroll_shadow_fact_secret.ps1 `
  -SecretFile 'C:\ProgramData\Kitling\BigQMT\host-facts\host-113-fact-shadow-20260917.json'
```

然后分别对 simulation 和 production_readonly 运行 `deliver_fact_outbox.py`；两次均使用 `--expected-host-id 10.10.10.113`。正式账户仍保持只读，Bridge 降级不触发重启或下单。

## `.121` 维护内容

客户端会自动把 `enroll_shadow_fact_secret.sh` 安装为：

```text
/home/kitling/bin/bigqmt-enroll-fact-host.sh
```

它仅更新：

```text
/etc/kitling-bigqmt-coordinator-shadow/fact-identities.json
```

更新前自动做带时间戳备份，保留原有 `.105` 条目；服务每次 facts POST 都重读该文件，因此无需重启 `18443` 或 Shadow 容器。合并后还会检查 Shadow 的健康状态和容器内实际可见的信任条目。

## 回报格式

只回报以下信息：

```text
host_id
key_id
enrollment success/failed
simulation delivery result
production_readonly delivery result
pending count
```

不要回传 Secret 内容、文件哈希、`secret_b64`、密码或本机 ACL 明细。
