# `.125` 当前执行单

`.125` Fact 已闭环：simulation / production_readonly 的 pending 均为 0，`.121` 已 ACTIVE 信任 `.125`，Redis 6379/6380 和两个 Bridge 已验证。当前只做版本同步和运行状态确认。

## 1. 同步最新分支

```powershell
Set-Location E:\kitling_QMT_work\kitling_bigqmt
git fetch origin "refs/heads/*:refs/remotes/origin/*"
git checkout host/125/structure
git pull --ff-only origin host/125/structure
git log -1 --oneline
```

应包含：

```text
5364838 fix: run protected shadow enrollment with sudo
25293bf chore: pin *.sha256 text eol=lf for sha256sum byte-equality
```

不要执行 `git reset --hard`，不要覆盖 `config\machine.local.json`、QMT 配置、Fact Secret、账户密码、授权 Key 或运行数据。

## 2. 只做运行确认

确认：

- 两个托盘仍在运行；
- Redis 6379 使用 `runtime_data\redis\simulation`；
- Redis 6380 使用 `runtime_data\redis\production_readonly`；
- simulation / production_readonly Fact delivery 继续返回 `ACCEPTED` 或 `EMPTY`，pending=0；
- simulation / production Bridge 状态正常；
- 正式账户保持只读。

可选地运行只读 intent-preview：

```powershell
py -3.12 scripts\probe_host_agent_intent_preview.py `
  --endpoint http://192.168.1.121:18443 `
  --host-id 192.168.1.125 `
  --account-id 90000001
```

## 3. 回报给 `.105`

只回报：

```text
git HEAD
两个托盘是否运行
6379/6380 状态
Fact pending 数量
simulation/prod Bridge 状态
intent-preview PASS/DEGRADED
```

不要重新签发 Secret，不要把 Secret 复制给其他主机，不要 push 旧的本地提交，不要执行任何正式下单。
