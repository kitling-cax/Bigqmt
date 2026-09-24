# `.125` / `.113` 托盘同步执行单

本次 Coordinator 可见性更新已发布到 GitHub 分支：

`feature/strategy-visibility-20260920`

请在本机工作目录执行（不要把策略包、Key、machine.local.json、运行数据提交到 Git）：

```powershell
git fetch origin
git switch feature/strategy-visibility-20260920
git pull --ff-only origin feature/strategy-visibility-20260920
pytest -q tests/test_host_agent_snapshot.py tests/test_host_agent_client.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_native_account_trays.ps1
```

编译成功后关闭旧的两个托盘，再启动新 EXE。检查：

1. 托盘仍显示本机授权 Key 状态、策略运行开关和删除策略入口。
2. 不要复制任何其他机器的 Secret/Key；本机配置和本机运行数据保持不变。
3. Coordinator 首页可以看到本机策略实例；`/api/v1/alerts` 只做网页提示。
4. 同一账户同一策略在多台主机同时 RUNNING 时，网页出现 `DUPLICATE_STRATEGY_RUNNING_ON_MULTIPLE_HOSTS`，不会自动停策略或删除 Key。

本次心跳只上报策略 ID/版本/运行状态/策略开关/授权状态/Bridge 版本，不上报 Key、密码、订单、委托或成交内容。
