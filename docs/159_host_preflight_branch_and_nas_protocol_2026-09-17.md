# .125 / .113 主机运行前预检与分支协议

## 1. Git 角色

| 主机 | Git 角色 | 允许动作 |
|---|---|---|
| `.105` | 集成主机 | 维护 `main`、打 tag、合并 PR、发布 NAS release |
| `.125` | 运行主机/开发分支 | `fetch`/`pull`、本地编译测试、推送 `host/125/*` 分支、提交 PR |
| `.113` | 运行主机/开发分支 | `fetch`/`pull`、本地编译测试、推送 `host/113/*` 分支、提交 PR |

`.125` 和 `.113` 不直接向 `main` 推送。即使本地误切到 `main`，运行前预检也必须拒绝“未发布或未匹配主机的提交”。GitHub 的主分支保护还应配置为只允许 `.105` 的维护者合并/发布；主机名称本身不能作为 GitHub 身份，因此必须同时使用仓库权限和分支规则。

## 2. NAS 发布物

NAS 只用于“发布说明、清单、私有本机配置和报告”，不作为运行目录。每次发布至少包含：

```text
release/<release-id>/
  README_INSTALL.md             # 本次发布说明和回滚方法
  manifest.json                 # release_id、git_commit、schema_version、适用主机
  checksums.sha256              # 发布物校验
  host-config/
    host-125.machine.local.json # 非密钥本机覆盖
    host-113.machine.local.json
  reports/
    build_report.md
    test_report.md
```

授权 Key、QMT 密码、Fact Secret 和 Redis 密码不放入公开 Git，也不放入普通明文 `machine.json`。它们通过本机首次初始化导入并用 DPAPI/Credential Manager 保存。

## 3. `.125/.113` 启动前固定顺序

### A. 读取 NAS 说明（显式动作）

1. 打开本次 `README_INSTALL.md`。
2. 读取 `manifest.json`，确认 `release_id`、目标 `host_id`、最低版本和回滚版本。
3. 读取 `checksums.sha256`，校验待复制的本地发布包。
4. 读取本机对应的 `host-125.machine.local.json` 或 `host-113.machine.local.json`，只导入路径、端口、账户、Coordinator 地址等非密钥字段。
5. NAS 不可达、说明缺失、清单不匹配或校验失败时：停止更新，保留旧版本；不得猜测继续执行。

### B. 同步 Git 到本地

```powershell
git fetch --prune origin
git switch host/125/runtime       # .125
git pull --ff-only origin host/125/runtime
# .113 使用 host/113/runtime
git show --no-patch --format=fuller <manifest.git_commit>
```

运行目录必须是本机磁盘，例如 `E:\kitling_QMT_work\kitling_bigqmt`；禁止从 NAS 共享目录直接运行 Python、托盘或 QMT。

### C. 导入本地配置

```powershell
py -3.12 scripts\bootstrap_private_config.py `
  --source "<NAS>\release\<release-id>\host-config\host-125.machine.local.json" `
  --root "E:\kitling_QMT_work\kitling_bigqmt" `
  --host-id "host-125"
```

`.113` 将 `host-125` 替换为 `host-113`。导入成功后，托盘启动只读取本机 `config/machine.local.json`/`local/machine.local.json`；NAS 可以立即断开。

### D. 本机门禁

1. 检查当前 Git commit 与 NAS `manifest.git_commit` 一致。
2. 检查 `machine.local.json` schema 和主机 ID。
3. 检查本机 QMT 根目录、Redis 端口、Bridge 端口和 Dashboard 端口。
4. 检查授权 Key 是否存在、账户/profile 是否匹配、是否过期；不打印 Key 原文。
5. 运行只读健康检查和编译/单元测试。
6. 只有门禁通过才启动托盘；Coordinator 不可达时仍可启动，但自动保持只读。

## 4. 版本回滚

若新版本预检失败或托盘启动异常：

1. 停止本机托盘和策略进程；
2. 保留 `local/state`、审计日志和诊断报告；
3. `git switch --detach <previous_git_commit>` 或恢复上一个本地发布目录；
4. 恢复对应的本机配置备份，不从 NAS 重新猜测；
5. 向 `.105` 提交失败报告，禁止直接修改 `main`。

## 5. 验收要求

- NAS 断开后，已初始化的托盘仍能启动；
- `.125/.113` 不能直接向 `main` 推送；
- 运行版本、主机 ID、账户和配置哈希都能在本地诊断报告中复现；
- 未授权/过期 Key、Coordinator 离线、QMT 未登录均只能产生只读状态；
- 任何配置更新都有发布 ID、Git commit、SHA-256 和回滚点。
