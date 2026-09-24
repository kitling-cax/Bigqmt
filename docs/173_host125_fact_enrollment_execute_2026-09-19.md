# `.125` 执行单：完成 Fact 100 条 pending 回传

`.125` 的代码、托盘、Redis 和两个 Bridge 已经通过验证。现在只处理 `.121` Shadow 对 `.125` 新 HMAC Secret 的信任注册。

## 1. 同步本次工具

```powershell
Set-Location E:\kitling_QMT_work\kitling_bigqmt
git fetch origin 'refs/heads/*:refs/remotes/origin/*'
git checkout host/125/structure
git pull --ff-only origin host/125/structure
git log -1 --oneline
```

确认历史包含：

本次注册工具修复；如果旧版本在注册时出现 `Permission denied`，先重新拉取分支再执行。

```text
6ac742e feat: add secure shadow fact enrollment workflow
```

## 2. 注册本机 Secret

确认文件存在，但不要打开、打印或复制其内容：

```powershell
Test-Path 'C:\ProgramData\Kitling\BigQMT\host-facts\host-125-fact-shadow-20260917.json'

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\coordinator\enroll_shadow_fact_secret.ps1 `
  -SecretFile 'C:\ProgramData\Kitling\BigQMT\host-facts\host-125-fact-shadow-20260917.json'
```

该命令会将 Secret 直接 SCP 到 `.121` 的受保护暂存目录，更新 Shadow 信任文件，并在成功后删除暂存副本。它不会将 Secret 写入 NAS、Git 或 `.105`。

## 3. 回归 delivery

先验证模拟 profile：

```powershell
py -3.12 scripts\host_agent\deliver_fact_outbox.py `
  --profile simulation `
  --secret-file 'C:\ProgramData\Kitling\BigQMT\host-facts\host-125-fact-shadow-20260917.json' `
  --outbox-path 'E:\kitling_QMT_work\kitling_bigqmt\runtime_data\state\simulation\host_agent_outbox.sqlite3' `
  --expected-host-id 192.168.1.125 `
  --endpoint http://192.168.1.121:18666/api/v1/facts/ingest
```

再将 profile 与 outbox path 替换为 `production_readonly`，执行一次。期望每次返回 `ACCEPTED` 或 `EMPTY`，pending 最终归零。

只回报 `host_id`、`key_id`、两次 delivery 结果和 pending 数量；不要回传 Secret 内容或 `secret_b64`。
