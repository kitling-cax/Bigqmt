# 184：Host Agent 策略安装拉取回归（`.125` / `.113`）

## 目的

验证 Coordinator 页面创建的策略安装请求能由目标托盘主动拉取、校验并安装到本机；安装后不自动启动策略，不改变 QMT 登录状态，不改变订单授权。

## 105 端已完成

- `.121:18443/strategies` 有“生成推送预览”和“请求安装（不启动）”；
- Coordinator 新增 `strategy_deployments` SQLite WAL 队列；
- Host Agent 使用：
  - `GET /api/v1/strategy-deployments?host_id=<本机 host_id>` 拉取；
  - `POST /api/v1/strategy-deployments/<deployment_id>/status` 回报 `INSTALLING/INSTALLED/FAILED`；
- 本机安装器校验 `MANIFEST.json` 全部 SHA-256，采用临时目录 + 原子目录切换；
- 托盘每 30 秒轮询一次，并新增“立即拉取策略安装请求（不启动）”菜单项；
- 安装结果写入本机 `runtime_data/strategies/installed/`，不写 QMT 配置，不调用订单接口。

## `.125` 和 `.113` 分别执行

在各自本地工作目录执行，不要从 NAS 直接运行：

```powershell
cd E:\kitling_QMT_work\kitling_bigqmt
git fetch origin 'refs/heads/*:refs/remotes/origin/*'
git checkout host/125/structure   # .125；.113 改为 host/113/structure
git pull --rebase origin host/125/structure   # .113 改为 host/113/structure
py -3.12 -m pytest tests/test_strategy_deployment.py tests/test_strategy_catalog_page.py -q
.\scripts\build_native_account_trays.ps1
```

确认 `config/machine.local.json` 增加本机私有配置（不要提交 GitHub）：

```json
{
  "strategy_deployment": {
    "library_root": "\\\\192.168.1.236\\truenas\\kitling_QMT\\kitling_bigqmt\\releases\\strategies\\candidate",
    "install_root": "E:\\kitling_QMT_work\\kitling_bigqmt\\runtime_data\\strategies\\installed"
  }
}
```

若 `.113` 不能使用 `192.168.1.236` 的 SMB 路径，应改成该机实际可达的 NAS 路径；不要把 NAS 路径写进公开仓库模板。

重启两个账户托盘后，在托盘菜单执行“立即拉取策略安装请求（不启动）”，确认：

1. 托盘显示“策略部署：无待安装请求”或“已安装（未启动）”；
2. `runtime_data/strategies/installed/<strategy_id>/<version>/<build_id>/INSTALL_RESULT.json` 存在；
3. Coordinator 页面请求状态为 `INSTALLED`；
4. `orders_enabled=false`、`run_after_install=false`；
5. QMT 中没有自动新增、停止或切换策略。

## 页面操作顺序

1. 打开 `http://192.168.1.121:18443/strategies`。
2. 勾选在线的 `.125` 或 `.113`。
3. 点击“生成推送预览”，确认目标为 `READY_TO_PULL`。
4. 点击“请求安装（不启动）”。
5. 等待目标托盘轮询，或在托盘菜单手动拉取。
6. 安装完成后，策略是否运行仍由目标托盘的本地策略开关和本地授权 Key 决定。

## 禁止事项

- 不要把 `machine.local.json`、QMT 密码、Fact Secret、授权 Key 提交 GitHub；
- 不要把正式账户策略安装请求当成正式下单授权；
- 不要在回归中点击策略启动或执行按钮；
- 不要让同一策略账户在多台主机同时进入 `ACTIVE_EXECUTOR`。

