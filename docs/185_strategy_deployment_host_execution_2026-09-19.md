# 185：策略候选推送与 Host 托盘安装执行单

## 目标

把 105 发布的框架分支同步到本机 125/113，重新编译包含 Host Agent 策略安装轮询功能的托盘。Coordinator 页面发出安装请求后，由目标托盘主动拉取、校验并安装策略；安装完成后不自动启动策略、不创建执行租约、不改变下单权限。

## 代码来源

- GitHub：`https://github.com/kitling-cax/Bigqmt`
- 发布分支：`feature/strategy-deployment`
- 本机长期运行分支：
  - `.125`：`host/125/structure`
  - `.113`：`host/113/structure`

## 2026-09-20 并发轮询修复

请再次合并 `origin/feature/strategy-deployment`（包含提交
`41874d3 fix: serialize host strategy deployment polling`）并重新编译。
该修复增加本机跨进程锁，避免模拟/正式托盘同时安装同一个策略包导致
`WinError 5`。第二个托盘会显示“其他托盘正在拉取”，不会重复安装或改变订单权限。

同时包含 `b058981 fix: allow failed strategy installs to retry`：旧的 FAILED 请求
再次点击页面按钮时会重新进入 REQUESTED，不会被旧幂等记录永久挡住。

## Claude 执行步骤（两台机器分别执行）

```powershell
cd E:\kitling_QMT_work\kitling_bigqmt
git fetch origin 'refs/heads/*:refs/remotes/origin/*'
git checkout host/125/structure       # 113 改成 host/113/structure
git pull --rebase origin host/125/structure  # 113 改成 host/113/structure
git merge --no-edit origin/feature/strategy-deployment
py -3.12 -m pytest tests/test_strategy_deployment.py tests/test_strategy_catalog_page.py -q
.\scripts\build_native_account_trays.ps1
```

若 merge 有冲突，先停止，不要覆盖本机 `machine.local.json`、凭据、Fact Secret、授权 Key 或运行数据；把冲突文件和错误报告给 105。

## 本机私有配置（不得提交 GitHub）

在本机 `config/machine.local.json` 增加：

```json
{
  "strategy_deployment": {
    "library_root": "\\\\192.168.1.236\\truenas\\kitling_QMT\\kitling_bigqmt\\releases\\strategies\\candidate",
    "install_root": "E:\\kitling_QMT_work\\kitling_bigqmt\\runtime_data\\strategies\\installed"
  }
}
```

`.113` 若无法访问该 SMB 路径，改为该机可访问的 NAS 路径。该文件只保存在本机，不提交、不推送。

## 编译后验证

1. 重启模拟和正式两个托盘。
2. 托盘菜单执行“立即拉取策略安装请求（不启动）”。
3. 确认托盘显示“无待安装请求”或“已安装（未启动）”。
4. 确认本机出现：
   `runtime_data/strategies/installed/<strategy_id>/<version>/<build_id>/INSTALL_RESULT.json`
5. 确认 `orders_enabled=false`、`run_after_install=false`。
6. 不点击任何策略启动、换仓或下单按钮。

## 105 Coordinator 页面操作

打开：`http://192.168.1.121:18443/strategies`

1. 选择候选策略。
2. 勾选在线的 `.125` 或 `.113`。
3. 点击“生成推送预览”，确认目标为 `READY_TO_PULL`。
4. 确认无误后点击“请求安装（不启动）”。
5. 等目标托盘轮询，或在托盘菜单手动拉取。

当前动作只安装策略包，不启动策略，不分配 ACTIVE_EXECUTOR，不改变模拟/正式账户下单权限。

## 禁止事项

- 不从 NAS 直接运行代码；必须复制到本机工作目录。
- 不提交 `machine.local.json`、QMT 密码、Fact Secret、授权 Key、Redis 密码和运行数据。
- 不把私有策略包提交到 GitHub。
- 不在两台主机同时启动同一策略账户。
- 不在正式交易时段执行 QMT/Redis 重启或策略切换。
