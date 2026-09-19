# `.125` 最新执行单（给 VS Code Claude）

目标：将 `.125` 本机同步到最新 `host/125/structure`，完成测试、托盘重编译和只读运行验证。

## 1. 同步代码

```powershell
Set-Location E:\kitling_QMT_work\kitling_bigqmt
git branch backup/host125-before-latest-20260919
git fetch origin
git checkout host/125/structure
git pull --ff-only origin host/125/structure
git log -1 --oneline
```

期望最新提交为：

```text
5721124 fix: reject placeholder host ids in portable bundles
```

不要执行 `git reset --hard`。不要覆盖本机 `config/machine.local.json`、QMT 配置、账户密码、Fact Secret、授权 Key 或运行数据。

## 2. 测试和编译

```powershell
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_native_account_trays.ps1
Get-FileHash tray\BigQMT_Simulation.exe,tray\BigQMT_Production_ReadOnly.exe -Algorithm SHA256
```

编译完成后再启动两个本机托盘。不要提交 EXE、日志、数据库或私有配置。

## 3. Fact Secret

`.125` 必须使用本机专属 Secret，且文件中的 host_id 必须是本机真实 host_id。不要从 `.105` 或 `.113` 复制 Secret。

如果出现 `FACT_HOST_ID_MISMATCH` 或 `fact_secret_missing`：

1. 停止托盘；
2. 核对 `config\machine.local.json` 的 host_id；
3. 由本机受保护 provisioner 重新签发 Secret；
4. 等 `.121` Shadow 把对应 key_id 加入受保护信任文件；
5. 再测试 Fact 投递。

HMAC Secret 没有可单独分发的“公钥”，Secret 不得经 Git、NAS、聊天或报告传输。

## 4. 只读运行验证

确认：

- Redis simulation 6379 UP；
- Redis production_readonly 6380 UP；
- 6380 使用 `runtime_data\redis\production_readonly`；
- simulation Bridge Ping PASS；
- production Bridge 未通过前保持只读；
- Fact 成功后返回 `ACCEPTED` 或 `EMPTY`，pending 逐步降到 0。

## 5. 不要做

- 不要 push 旧的本地 checksums/runbook 提交；
- 不要把 `.125` Secret 发给 `.105`；
- 不要把正式账户切换为可下单；
- 不要在交易时段自动 stop/start Redis；
- 不要修改 host_id 去迁就旧 Secret。

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
