# `.125` / `.113` Claude 托盘重新编译执行单（2026-09-20）

适用于 `.125` 和 `.113`。用户消息中的“133”按项目上下文理解为 `.113`；如确实存在 `.133`，使用相同步骤和对应分支。

## 目标

同步到 GitHub `feature/tray-authorization-key` 最新提交 `6b10303`，包含：

- 授权 Key 加入、删除、状态显示；
- 授权 Key 最少 10 个字符；
- 删除授权 Key 需要托盘删除密码和二次确认；
- 设置/修改托盘删除密码；
- 策略运行开关和删除已安装策略；
- QMT、MiniQMT、Redis、Bridge、Dashboard、Host Agent 状态监控。

本次只更新程序，不复制账户密码、QMT 凭据、授权 Key、Fact Secret、Redis 数据或日志。

## Git 同步

先确认工作区，不得 reset、clean、stash 或覆盖未提交改动。工作区不干净时停止并报告。

```powershell
cd E:\kitling_QMT_work\kitling_bigqmt
git status --short
git fetch origin "refs/heads/*:refs/remotes/origin/*"
```

`.125`：

```powershell
git switch host/125/structure
git pull --ff-only origin host/125/structure
git merge --no-ff origin/feature/tray-authorization-key
```

`.113`：

```powershell
git switch host/113/structure
git pull --ff-only origin host/113/structure
git merge --no-ff origin/feature/tray-authorization-key
```

必须包含提交：`f1fe047`、`ab35284`、`6b10303`。出现冲突时停止，不要自行覆盖。

## 测试和编译

```powershell
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_native_account_trays.ps1
Get-FileHash tray\BigQMT_Simulation.exe,tray\BigQMT_Production_ReadOnly.exe -Algorithm SHA256
```

哈希必须与 `tray\BigQMT_native_tray_checksums.sha256` 一致。若 EXE 被占用，先退出两个旧托盘再编译。禁止提交 `machine.local.json`、`runtime_data` 和任何凭据。

## 启动与菜单验收

退出旧托盘，启动新编译的两个 EXE，保留本机原有配置。右键两个托盘确认存在：

1. `下单授权 Key 管理`；
2. `查看本账户 Key 状态`；
3. `加入本账户授权 Key`；
4. `设置/修改托盘删除密码`；
5. `删除本账户授权 Key`；
6. `策略运行开关`；
7. `删除已安装策略（需要密码）`。

首次使用时，在每台机器本地分别设置：删除密码至少 8 位，授权 Key 至少 10 位。两类密码都不得通过 Git、NAS 或聊天传输。

## 回报格式

只回报非敏感信息：

```text
host_id=
git_head=
pytest=PASS/FAIL
tray_build=PASS/FAIL
authorization_key_menu=PASS/FAIL
delete_password_menu=PASS/FAIL
strategy_delete_menu=PASS/FAIL
simulation_tray=RUNNING/STOPPED
production_tray=RUNNING/STOPPED
```

正式账户仍受 `production_readonly` 保护；安装正式 Key 不会单独开放正式下单。
