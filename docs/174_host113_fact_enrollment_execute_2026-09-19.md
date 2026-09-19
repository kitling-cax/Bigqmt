# `.113` 执行单：签发并注册本机 Fact Secret

`.113` 已同步至 `9b2e68f`，含 `221fde4` 与 `6765a8d`；275 项测试通过，Redis 和模拟 Bridge 正常。现在只补齐 `.113` 自己的 Fact Secret 和 `.121` Shadow 信任注册。

## 1. 同步本次工具

```powershell
Set-Location E:\kitling_QMT_work\kitling_bigqmt
git fetch origin 'refs/heads/*:refs/remotes/origin/*'
git checkout host/113/structure
git pull --ff-only origin host/113/structure
git log -1 --oneline
```

确认历史包含：

```text
72bca52 feat: add secure shadow fact enrollment workflow
```

不要对已经保留的 `backup/host113-before-latest-20260919` 做 rebase、push 或 reset。

## 2. 本机签发与注册

`.113` 的真实 host_id 是 `10.10.10.113`。在本机执行：

```powershell
py -3.12 scripts\coordinator\manage_fact_identity.py `
  --host-id 10.10.10.113 `
  --key-id host-113-fact-shadow-20260917 `
  --output 'C:\ProgramData\Kitling\BigQMT\host-facts\host-113-fact-shadow-20260917.json'

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\coordinator\enroll_shadow_fact_secret.ps1 `
  -SecretFile 'C:\ProgramData\Kitling\BigQMT\host-facts\host-113-fact-shadow-20260917.json'
```

如果目标 Secret 文件已存在，停止并回报，不要覆盖或从任何其他机器复制。注册脚本直接把本机 Secret 传到 `.121` 受保护暂存目录，成功后清理暂存副本。

## 3. 回归 delivery

分别运行 simulation 与 production_readonly 的 `deliver_fact_outbox.py`。两次均使用：

```text
--expected-host-id 10.10.10.113
--endpoint http://192.168.1.121:18666/api/v1/facts/ingest
```

期望 `ACCEPTED` 或 `EMPTY`。正式账户继续只读；production Bridge 的 `DEGRADED` 只记录，不重启 QMT/Bridge，也不触发订单。

只回报 `host_id`、`key_id`、两次 delivery 结果和 pending 数量；不要回传 Secret 内容或 `secret_b64`。
