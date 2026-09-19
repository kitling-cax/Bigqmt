# `.113` 最新执行单（给 VS Code Claude）

目标：将 `.113` 本机同步到最新 `host/113/structure`，完成测试、托盘重编译和只读运行验证。

## 1. 同步代码

```powershell
Set-Location E:\kitling_QMT_work\kitling_bigqmt
git branch backup/host113-before-latest-20260919
git fetch origin
git checkout host/113/structure
git pull --ff-only origin host/113/structure
git log -1 --oneline
```

期望最新提交为：

```text
6765a8d fix: reject placeholder host ids in portable bundles
```

该分支已经包含 `221fde4 fix: repair host fact identity redis paths and deterministic trays`。

不要执行 `git reset --hard`。不要覆盖本机 `config/machine.local.json`、QMT 配置、账户密码、Fact Secret、授权 Key 或运行数据。

如果本地存在 `bc30e5b`、`c59453f` 等未推送提交，不要直接 push；先完成上述同步，再确认差异后决定是否重新生成必要提交。

## 2. 测试和编译

```powershell
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_native_account_trays.ps1
Get-FileHash tray\BigQMT_Simulation.exe,tray\BigQMT_Production_ReadOnly.exe -Algorithm SHA256
```

编译完成后再启动两个本机托盘。不要提交 EXE、日志、数据库或私有配置。

## 3. `.113` 专属 Fact Secret

`.113` 必须由本机受保护 provisioner 签发独立 Secret，host_id 使用本机真实值：

```text
10.10.10.113
```

不要从 `.105` 或 `.125` 复制 Secret。HMAC Secret 没有可单独分发的“公钥”，Secret 不得经 Git、NAS、聊天或报告传输。

如果出现 `fact_secret_missing`：

1. 停止托盘；
2. 按本机 provisioner 生成 `.113` 专属 Secret；
3. 把 key_id/host_id 元数据交给 `.105`，不要发送 Secret 内容；
4. 等 `.121` Shadow 将该 key 加入受保护信任文件；
5. 再测试 simulation 和 production_readonly 的 Fact 投递。

## 4. 只读运行验证

确认：

- Redis simulation 6379 UP；
- Redis production_readonly 6380 UP；
- 6380 使用 `runtime_data\redis\production_readonly`；
- simulation Bridge Ping PASS；
- production Bridge DEGRADED 时保持只读，不执行正式订单；
- Fact 成功后返回 `ACCEPTED` 或 `EMPTY`，pending 逐步降到 0。

## 5. 不要做

- 不要直接 push 旧的 `bc30e5b`、`c59453f`；
- 不要把 `.113` Secret 发给 `.105`、`.125` 或写入 NAS；
- 不要把正式账户切换为可下单；
- 不要在交易时段自动 stop/start Redis；
- 不要把 host_id 改成 `192.0.2.113` 等测试占位值。

## 6. 回报给 `.105`

请只回报：

```text
git commit
pytest passed/failed
两个 EXE SHA-256
6379/6380 状态
Fact 状态（不含 Secret）
simulation/prod Bridge Ping 状态
```
