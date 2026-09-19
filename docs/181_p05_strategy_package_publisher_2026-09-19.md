# P05 策略包发布器首版（2026-09-19）

## 本轮完成

新增 `scripts/publish_strategy_package.py`，把已登记策略源码构造成不可变本地发布物：

```text
releases/strategies/<strategy_id>/<version>/<build_id>/
├── payload/                 # 策略源码，只允许普通发布文件
├── registry_entry.json      # 发布时锁定的策略登记快照
├── MANIFEST.json            # strategy_package_manifest.v1
├── checksums.sha256         # 每个 payload 与清单的 SHA-256
└── release_result.json
<strategy_id>-<version>-<build_id>.zip
```

发布器是离线工具，不连接 QMT、Redis、Coordinator，不读密码，不产生订单。
它会拒绝 `.env`、`machine.local.json`、`runtime_data`、日志、outbox、password、secret、token、credential 等敏感或运行期文件；不会覆盖已有 `build_id`。

## 首个策略包示例

```powershell
py -3.12 scripts\publish_strategy_package.py `
  --strategy-id S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15 `
  --version v1.1.15 `
  --build-id 20260919-r1 `
  --source <本机策略源码目录>
```

生成后应人工复核 `MANIFEST.json`、`checksums.sha256` 和 `registry_entry.json`，再由发布流程复制到 NAS 的 candidate/stable 策略库。NAS 只做分发和归档，目标机必须复制到本地后安装；托盘运行不依赖 NAS。

## 安全边界

- `orders_enabled=false` 固定写入发布结果；
- `formal_account_allowed=false` 从策略注册表再次校验；
- 当前工具只负责 P05 包装与校验，不会启用 v1.1.15 模拟下单；
- 模拟盘实际启用仍由独立的 P06 批准和本机授权闸门决定；
- 正式账户不会因发布策略包而获得任何权限。

## 验证

新增 `tests/test_strategy_package_publisher.py`，覆盖正常构建、敏感文件拒绝和版本漂移拒绝。先在 `.105` 完成包构建回归，再进入 NAS candidate 发布和 `.125/.113` 本地安装测试。
