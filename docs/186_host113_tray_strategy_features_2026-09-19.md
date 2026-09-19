# 186：`.113` 托盘策略控制功能执行单（fetch → 合并 → 编译 → 验证）

## 目的

把 `.125` 已经验证好的一组托盘策略控制功能落到 `.113`：每策略运行开关、「删除已安装策略」密码门禁、卸载后清策略、菜单反映本机实际安装状态。**本单按顺序执行可一次通过**，不用逐台反复试错。

## 前置概念（照做就对，不用临时推断）

| 概念 | 说明 |
|---|---|
| 两套托盘 | 原生 C# exe（`BigQMT_Simulation.exe` / `BigQMT_Production_ReadOnly.exe`）才是本单目标；Python/PowerShell 那套 `launch_tray_detached.py` 是遗留实现，**不要用它** |
| 进程名陷阱 | PS 托盘进程名是 `powershell.exe`，tasklist 查 `BigQMT_*.exe` 会漏掉；判断托盘是否在跑用下面的 PowerShell 命令 |
| exe 锁 | 编译前必须先杀托盘，否则 csc 报 `CS0016 文件被占用` |
| 密码 | `tray.delete_strategy_password_sha256` 是你自己的密码的 SHA-256，**任何密码/散列都不要写进本货仓文档或 commit** |
| 本地即真理 | 菜单「策略部署」与「策略运行开关」读本机 `runtime_data/strategies/installed/` 与 `config/strategy_runtime_policy.json`，Coordinator 只负责投递 |

## 步骤

### 1. 拉代码并合并（在 `.113` 本地工作目录，不要从 NAS 直接跑）

```powershell
cd E:\kitling_QMT_work\kitling_bigqmt
git fetch origin 'refs/heads/*:refs/remotes/origin/*'
git checkout host/113/structure
# 若本机分支已有自己改动：先看 git status，不要覆盖 machine.local.json / 凭据 / 运行数据
git merge --no-edit origin/feature/tray-strategy-control
```

若 merge 冲突，停下来不猜；把冲突文件名和 `git diff --check` 输出报告给 105/125，不要自己乱解。

### 2. 无头验证（先确认 Python 链路通，再动 GUI）

```powershell
py -3.12 -m pytest tests/test_strategy_deployment.py tests/test_strategy_catalog_page.py tests/test_uninstall_strategy_package.py tests/test_set_strategy_auto_run.py -q
py -3.12 scripts/verify_host_tray_features.py
```

预期：pytest 12 passed；verify 全 PASS。任何 FAIL 先停下报告，不要继续编译。

### 3. 配置 `config/machine.local.json`（只留本机，不提交）

- `strategy_deployment.install_root`：`E:\kitling_QMT_work\kitling_bigqmt\runtime_data\strategies\installed`
- `strategy_deployment.library_root`：`.113` 实际可达的 NAS 路径（`Z:` 映射或 UNC 都行，先 `Test-Path` 验一下；`192.168.1.236` 的 UNC 在部分主机不可达，用映射盘）
- `tray.delete_strategy_password_sha256`：**自己生成**，不要在货仓里贴密码或散列：
  ```powershell
  printf '%s' 'YOUR_PASSWORD' | sha256sum
  ```
  把输出的小写 64 位 hex 填进该字段再删掉中间的空格。
- `config/machine.local.json` 已在 `.gitignore`，**绝不 `git add`**。

### 4. 杀掉所有托盘再编译（这步是以前 build 失败的头号原因）

```powershell
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'BigQMT_*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Start-Sleep 3"
# 顺带清掉遗留的 PS 托盘（进程名是 powershell.exe）
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'powershell.exe' -and $_.CommandLine -like '*BigQMTTray.ps1*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_native_account_trays.ps1
```

预期：只有 `warning CS0429/CS0162`（profile 短路分支，全部无害），无 `error`。若报 `CS0016`，说明还有托盘/防病毒锁着 exe，等 10 秒重试或手动杀净。

### 5. 启动两个原生托盘

```powershell
powershell -NoProfile -Command "Start-Process -FilePath 'E:\kitling_QMT_work\kitling_bigqmt\tray\BigQMT_Simulation.exe' -WorkingDirectory 'E:\kitling_QMT_work\kitling_bigqmt' -WindowStyle Hidden"
powershell -NoProfile -Command "Start-Process -FilePath 'E:\kitling_QMT_work\kitling_bigqmt\tray\BigQMT_Production_ReadOnly.exe' -WorkingDirectory 'E:\kitling_QMT_work\kitling_bigqmt' -WindowStyle Hidden"
```

### 6. 手工验证清单（点一次，全满足即算过）

模拟盘右键：
1. 「策略部署」显示 `已安装（未启动）; 本地 N 条` 或 `无待安装请求; 本地无安装`
2. 「**策略运行开关**」子菜单：每装一条策略一行 `启用 <strategy_id> 自动运行`；点勾/取消 → 弹回与 `config/strategy_runtime_policy.json::simulation.strategies.<id>.auto_run_enabled` 同步
3. 「**删除已安装策略（需要密码）**」→ 输错密码弹「密码错误」→ 输对后出现 **ListBox**（点行高亮多选）→ 勾 0 行时「删除选中」变灰 → 选中后二次确认 → 输错/取消全程有 audit
4. 删除后：菜单「策略部署」变「本地无安装」；对应策略的运行开关行消失；policy 里该策略条目被清掉
5. `Runtime_data/audit/<profile>/native_tray.jsonl` 应有 `strategy_uninstalled` / `strategy_policy_cleared` / `strategy_policy enabled|disabled <id>` 事件

正式盘右键：**不应**有「删除已安装策略」「策略运行开关」；「允许已批准正式策略恢复意图」保持只读意图提示。

## 已知差异（当前阶段，非缺陷）

- S99 这类无运行脚本的安装策略：开关能存状态、能清，但**不驱动任何周期**（等运行脚本接入）。v1.1.15 的开关真正门禁订单周期。
- Coordinator `strategy_deployments` 队列里已 `INSTALLED` 的记录不因本机删除而清（仓库无 DELETE 端点）；重推同 build_id 会判 `ALREADY_INSTALLED`，要先删本机目录才可能重装。
- 「策略运行开关」子菜单只有模拟盘有；正式盘只读。

## 禁止事项

- 不提交 `machine.local.json`、明文密码、密码散列、Fact Secret、QMT 密码、Redis 密码、运行数据到 GitHub
- 不从 NAS/拖到共享盘直接运行代码；必须在本机工作目录
- 不在两台主机同时跑同一策略账户
- 不在正式交易时段重启 QMT/Redis 或切策略
- 不把任何密码字符串写进本货仓的任何 doc / commit / 日志