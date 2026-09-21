# 三台主机托盘功能同步单（2026-09-20）

## 结论

`.105`、`.125`、`.113` 的托盘可以有不同的账户、授权 Key、已安装策略和运行开关；但以下程序功能必须来自同一代码版本：

- 授权 Key 加入、删除、状态显示；
- 策略安装请求拉取、策略运行开关、删除已安装策略；
- QMT、MiniQMT、Redis、Bridge、Dashboard、Host Agent 状态监控；
- 本地策略日志、事实 Outbox 和每日运行证据；
- 订单入口统一经过本机授权 Key 和既有执行门禁。

Key、QMT 凭据、`machine.local.json`、策略运行数据和日志均不得跨机器复制。

## 当前检查

- `.105`：源码已加入授权 Key 菜单和删除策略菜单，正在重建本机托盘；
- `.125`：删除策略菜单已有，授权 Key 菜单尚未合入；
- `.113`：删除策略菜单已有，授权 Key 菜单尚未合入；
- 187 文档已分别放入 `.125`、`.113` 共享目录。

## `.125` / `.113` Claude 执行步骤

在本机工作目录执行，不读取或提交任何 Key：

```powershell
git fetch origin 'refs/heads/*:refs/remotes/origin/*'
git switch host/125/structure       # .125 使用本机分支
git pull --ff-only origin host/125/structure
git merge --no-ff origin/feature/tray-authorization-key
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_native_account_trays.ps1
```

`.113` 将上面的 `host/125/structure` 改成 `host/113/structure`。如果本机分支存在未提交工作，先停止并报告，不要 reset、stash 或覆盖用户改动。

编译完成后退出旧托盘，替换本机两个托盘 EXE，再启动。用右键菜单确认以下菜单同时存在：

1. `下单授权 Key 管理`；
2. `策略运行开关`；
3. `删除已安装策略（需要密码）`；
4. `立即拉取策略安装请求（不启动）`。

## 验收

- 未加入 Key：托盘显示“账户只读”，只读查询仍可用；
- 加入 Key：仅当前 profile、当前账户显示有效；
- 删除 Key：无需重启，立即恢复只读；
- 删除 Key：必须先通过本机托盘删除密码，再二次确认；
- 不同机器可安装不同 Key，不能把 Key 文件、密码或凭据库导出到 NAS；
- 每台机器可以运行不同策略；同一账户多机运行时由 Coordinator 网页报警，不自动降级或阻断；
- 正式账户当前仍保持 `production_readonly`，加入 Key 不会单独打开正式下单。

## 回报格式

只回报以下非敏感信息：

```text
host_id=
git_head=
pytest=
tray_build=PASS/FAIL
key_menu=PASS/FAIL
strategy_delete_menu=PASS/FAIL
simulation_tray=RUNNING/STOPPED
production_tray=RUNNING/STOPPED
```

禁止回报 Key 内容、QMT 密码、Credential Manager 内容、`machine.local.json` 全文和运行数据库。
