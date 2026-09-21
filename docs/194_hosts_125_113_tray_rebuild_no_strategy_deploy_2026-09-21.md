# `.125` / `.113` 托盘同步重编译执行单

日期：2026-09-21  
发布主机：`.105`  目标：同步托盘功能，不部署策略

## 本次更新内容

- 修复本地策略安装列表读取，恢复“策略运行开关”菜单；
- 新增 `策略运行状况` 状态行，显示策略名称、开关、Bridge 状态和订单窗口状态；
- 显示“模拟授权有效 / 当前订单窗口关闭”，避免把授权状态与临时订单窗口混淆；
- 增加策略开关脚本、策略卸载脚本及授权 Key 管理脚本；
- 保持正式账户只读；
- 保持 `.125`、`.113` 暂不安装、启动或执行 v1.1.15 策略。

## GitHub 来源

仓库：`https://github.com/kitling-cax/Bigqmt.git`  
发布分支：`feature/nas-private-config`  
发布提交：由 `.105` 负责人在消息中提供本次最新 commit hash。

## `.125` 执行步骤

在本机 `E:\kitling_QMT_work\kitling_bigqmt` 工作目录打开 VS Code/Claude 终端：

```powershell
git fetch origin --prune
git status --short
git branch --show-current
git cherry-pick <本次发布commit>
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_native_account_trays.ps1
```

如本机已有未提交修改，不要 reset 或覆盖；先创建备份分支并报告冲突：

```powershell
git branch backup/host125-before-tray-status-20260921
```

编译后只启动托盘，不部署策略：

```powershell
Get-Process -Name BigQMT_Simulation,BigQMT_Production_ReadOnly -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process .\tray\BigQMT_Simulation.exe
Start-Process .\tray\BigQMT_Production_ReadOnly.exe
```

验证：

1. 模拟托盘菜单出现“策略运行状况”；
2. 模拟托盘显示“暂未安装策略”或“策略未部署”，不得出现已安装 v1.1.15；
3. 正式托盘显示 `BIGQMT_BRIDGE｜正式只读`；
4. 两个账户均为 `orders_enabled=false`；
5. 不复制策略包、不点击策略安装、不启动 v1.1.15。

## `.113` 执行步骤

与 `.125` 相同，在本机 `E:\kitling_QMT_work\kitling_bigqmt` 执行：

```powershell
git fetch origin --prune
git status --short
git branch --show-current
git cherry-pick <本次发布commit>
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_native_account_trays.ps1
Get-Process -Name BigQMT_Simulation,BigQMT_Production_ReadOnly -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process .\tray\BigQMT_Simulation.exe
Start-Process .\tray\BigQMT_Production_ReadOnly.exe
```

同样只验证托盘菜单和只读状态，不安装、不运行策略。

## 禁止事项

- 不要复制 `.105` 的 `machine.local.json`、授权 Key、QMT 凭据、Fact Secret、Redis 数据或运行数据库；
- 不要把 `.105` 的策略安装目录复制到目标机；
- 不要开启正式账户策略恢复；
- 不要在交易时段重启 QMT 或 Redis；
- 不要将本机密钥、密码、日志和 `runtime_data` 提交 GitHub。

## 回报格式

请回报以下信息：

```text
host_id:
git HEAD:
pytest:
tray build:
simulation tray:
production tray:
strategy installed: NO
orders_enabled: false
```
