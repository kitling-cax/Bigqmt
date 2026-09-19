# `.113` Claude 执行单：Host 修复与托盘重编译

> 目标：在 `.113` 本机完成代码同步、编译、测试和现场只读验证。
> 禁止把密码、Fact Secret、授权 Key、`machine.local.json` 私有内容提交到 Git。

## 1. 同步正确分支

在 VS Code 终端执行：

```powershell
Set-Location E:\kitling_QMT_work\kitling_bigqmt
git fetch origin
git checkout host/113/structure
git pull --ff-only origin host/113/structure
git log -1 --oneline
```

期望看到修复提交：`221fde4 fix: repair host fact identity redis paths and deterministic trays`。

如果工作区有本机私有修改，先备份；不要执行 `git reset --hard`，不要覆盖 `config/machine.local.json`、本机 Fact Secret 或 QMT 配置。

## 2. 编译和测试

```powershell
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_native_account_trays.ps1
Get-FileHash tray\BigQMT_Simulation.exe,tray\BigQMT_Production_ReadOnly.exe -Algorithm SHA256
```

编译成功后，两个 EXE 必须存在。编译器出现已知的不可达分支 warning 可以记录，但不能有 error。

## 3. 核对本机身份（只读）

```powershell
Get-Content config\machine.local.json
```

`.113` 的 `host_id` 必须是本机实际值（通常为 `10.10.10.113`）；不要使用 `192.0.2.113` 这类测试占位值。

不要从 `.105` 或 `.125` 复制账户密码、Fact Secret 或授权文件。它们必须是 `.113` 独立生成的本机文件。

## 4. Fact 投递验证

先从本机配置或托盘日志确认 Secret 文件、Outbox 路径，再执行对应 profile 的只读投递检查。命令中的路径必须替换为本机实际路径：

```powershell
py -3.12 scripts\host_agent\deliver_fact_outbox.py `
  --profile simulation `
  --secret-file <本机simulation Fact Secret> `
  --outbox-path <本机simulation outbox.sqlite3> `
  --expected-host-id 10.10.10.113 `
  --endpoint http://192.168.1.121:18666
```

正式 profile 同样检查，但不要因此放开正式下单。若输出 `FACT_HOST_ID_MISMATCH`，停止托盘并重新签发 `.113` 专属 Secret；不要改 `machine.local.json` 去迁就错误 Secret。

## 5. Redis 和 Bridge 现场验证

启动 QMT、`BIGQMT_BRIDGE` 和托盘后检查：

- 模拟 Redis：6379 UP；
- 正式 Redis：6380 UP，运行目录为 `runtime_data\redis\production_readonly`；
- 托盘状态中 Fact 不再出现 host_id mismatch；
- 模拟 Bridge 只读 Ping PASS 后才允许策略路径继续；
- 正式 Bridge 如果 DEGRADED，保留只读状态并记录日志，不执行正式订单。

## 6. 回报格式

请把以下内容回报给 `.105`：

1. `git log -1 --oneline`；
2. `pytest` 总数和失败数；
3. 两个 EXE 的 SHA-256；
4. Redis 6379/6380 状态；
5. Fact 投递结果（只回状态、不要回 Secret）；
6. Bridge Ping 结果和错误日志路径。

完成后只提交代码修复，不提交本机配置、日志、数据库、Secret 或 EXE 私有运行数据。
