# BigQMT 协作与发布规则

## 主机职责

- `192.0.2.105`：唯一集成与发布主机。维护 `main`、审查 PR、创建 tag、发布
  NAS 构建包；开发期间也是唯一模拟 `ACTIVE_EXECUTOR` 候选。
- `192.0.2.125`：未来优先策略运行主机。仅在自身分支修改、编译、部署验证后
  发 PR；未获 Coordinator 明确授权时保持只读。
- `198.51.100.113`：未来备用策略运行主机。规则同 `.125`，默认
  `STANDBY_READONLY`。
- `192.0.2.121`：Coordinator 容器主机。只协调事实、状态和唯一执行权，不运行
  QMT 或直接下单。

## 分支规则

```text
main                    # 仅 .105 集成
host/105/<topic>        # Codex 开发
host/125/<topic>        # .125 本机验证
host/113/<topic>        # .113 本机验证
release/v<major>.<minor># 可选稳定维护线
```

不得直接推送 `main`。每次 `.125/.113` 的变更都要经过本机测试、PR 和 `.105`
集成。一个账户可有多个在线 QMT，但永远只能有一个 Coordinator 批准的执行主机。

当前私有仓库的 GitHub Free 套餐不支持平台级 Branch Protection/Rulesets。此限制
不降低运行安全门禁：在升级 GitHub Pro/Team 前，`main` 的人工门禁由 `.105` 执行，
只能合并两项 CI 均为绿色且 PR 模板完整的变更；禁止 `.125/.113` 直接推送 `main`。

## 提交前门禁

```powershell
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_portable_host_bundles.ps1
git diff --check
git status
```

不要提交：`config/machine.local.json`、QMT/券商密码、Fact Secret、执行授权 Key、
SQLite/WAL、Redis 数据、运行日志、EXE 或发布包。编译包只用 SHA-256 manifest
发布到 NAS 或 GitHub Release。

## 发布

`.105` 合并并验证后创建带注释 tag，例如 `v0.3.0`。同一 tag 的 Coordinator
容器、Host Tray 和 Windows 部署报告必须记录协议 `schema_version` 与兼容性。先
验证 `.121:18666` Shadow，再讨论权威 Coordinator 升级；不得把容器发布视为
订单授权。
