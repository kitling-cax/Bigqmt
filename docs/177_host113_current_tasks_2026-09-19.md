# `.113` 当前执行单

`.113` 代码、托盘、Redis 和 Fact 投递已经闭环。当前只做版本同步、Coordinator intent-preview 网络验证，以及非交易时段正式 Bridge 的只读恢复检查。

## 1. 同步最新分支

```powershell
Set-Location E:\kitling_QMT_work\kitling_bigqmt
git fetch origin "refs/heads/*:refs/remotes/origin/*"
git checkout host/113/structure
git pull --ff-only origin host/113/structure
git log -1 --oneline
```

应包含：

```text
690a029 fix: run protected shadow enrollment with sudo
```

不要 push 旧的 `bc30e5b`、`c59453f`，不要执行 `git reset --hard`，不要覆盖 `machine.local.json`、Fact Secret、授权 Key、QMT 配置或运行数据。

## 2. 验证 Coordinator intent-preview

```powershell
py -3.12 scripts\probe_host_agent_intent_preview.py `
  --endpoint http://192.168.1.121:18443 `
  --host-id 10.10.10.113 `
  --account-id 90000001
```

如果失败，再执行：

```powershell
Test-NetConnection 192.168.1.121 -Port 18443
```

只记录网络结果，不修改 Coordinator 地址，不切换到 18666；18666 只用于 Fact 投递。

## 3. 正式 Bridge 只读恢复检查

非交易时段才执行。先确认正式账户仍为只读，然后按本机既有托盘菜单或 QMT 操作重启正式 QMT/Bridge。重启后确认：

- production Bridge Ping 返回 `PASS`；
- `orders_enabled=false`；
- `broker_call_made=false`；
- 没有正式订单、撤单或策略写入。

如果仍为 `DEGRADED`，保留日志并停止继续重启，不修改桥接代码。

## 4. 回报给 `.105`

```text
git HEAD
intent-preview PASS/DEGRADED
Test-NetConnection 结果（如执行）
production Bridge PASS/DEGRADED
orders_enabled 是否始终 false
Fact pending 数量
```

不要重新生成或复制 Fact Secret，不要开启正式账户下单。
