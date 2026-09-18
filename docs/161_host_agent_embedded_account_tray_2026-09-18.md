# Host Agent 与账户托盘合并实施记录

日期：2026-09-18  
状态：本机编译验证通过，待部署到 `.125/.113` 运行主机  
适用程序：`BigQMT_Simulation.exe`、`BigQMT_Production_ReadOnly.exe`

## 本次改动

Host Agent 不再要求单独启动 `BigQMTHostAgentTray.exe`。账户托盘自身负责：

- 每次状态刷新时发送脱敏 Coordinator 心跳。
- 周期性采集本账户托盘审计事实。
- 将事实写入本机 SQLite WAL Outbox。
- 每五分钟向 Shadow Coordinator `18666` 投递签名事实并处理 ACK。
- 网络失败时保留 Outbox，下一轮自动重试。
- Coordinator 或 NAS 不可用时不停止本地 QMT、Bridge、策略和订单状态机。
- 退出托盘只停止 Host Agent 心跳/投递，不删除本地策略状态、日志或 Outbox。

## 配置改进

账户托盘现在读取本机 `config/machine.local.json`：

```json
{
  "coordinator": {
    "endpoint": "http://<COORDINATOR_HOST>:18443",
    "host_id": "<LOCAL_HOST_ID>"
  },
  "host_agent": {
    "fact_secret_path": "C:/ProgramData/Kitling/BigQMT/host-facts/host-125-fact-shadow-20260917.json"
  }
}
```

- `host_id` 不再写死为 `.105`。
- 事实投递端点由 `coordinator.endpoint` 自动改为同一主机的 `18666`。
- Fact Secret 支持本机配置路径；没有配置时只尝试本机标准目录，不访问 NAS。
- 模拟和正式账户托盘共享 Host Agent 身份，但每个账户事实仍带独立 profile/account 标识。
- Fact Secret 内容不进入 Git、策略包、日志或 Coordinator 响应。

## 托盘界面

账户托盘菜单新增：

```text
Host Agent：心跳正常｜<host_id>｜只读服务已上报
```

异常时显示：

- `心跳失败`：Coordinator暂时不可达，本地继续运行。
- `等待 Fact Secret`：本机授权文件未安装。
- `采集失败`：本地审计事实暂时无法生成。
- `事实待重试`：事实保留在 Outbox，等待下轮补传。
- `事实投递正常`：Outbox已确认。

Host Agent 状态不会单独把账户交易状态改成红色；账户红色仍只表示 QMT、MiniQMT、Redis、Dashboard 或 Bridge 等关键本地服务异常。

在“服务管理”中还提供“立即同步 Host Agent（只读）”，用于人工触发一次心跳和 Outbox 补传。该动作在后台线程执行，网络超时不会卡住托盘菜单。

## 编译验证

执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_native_account_trays.ps1
```

结果：两个 EXE 编译成功。当前哈希记录在：

`tray/BigQMT_native_tray_checksums.sha256`

本机 Host Agent/Coordinator 相关回归：

```text
17 passed
```

## 三台主机部署规则

### `.105`

使用 `.105` 本机 `machine.local.json`，账户托盘负责本机 Host Agent。开发期间可上报 18666 Shadow 事实。

### `.125`

1. 从 GitHub 获取批准分支或 Release Tag。
2. VS Code（Claude）执行本机编译脚本。
3. 将 `.125` 的 `machine.local.json`、Fact Secret 和 QMT路径保留在本机。
4. 启动账户托盘，不再启动独立 Host Agent 托盘。
5. 菜单出现 `Host Agent：心跳正常` 后，检查本机配置中的 Shadow Coordinator 地址 `/api/v1/hosts`。

### `.113`

流程与 `.125` 相同，但使用 `.113` 自己的 `host_id` 和 Fact Secret。不能复制 `.125` 的 Fact Secret 到 `.113`。

## 验收标准

- 两个账户托盘都能显示 Host Agent 状态。
- 关闭 Coordinator 后，托盘仍可运行，Outbox保持 pending。
- 恢复 Coordinator 后，Outbox自动 ACK并清理已确认事件。
- `.125` 和 `.113` 的心跳 host_id 不相同。
- 相同机器的模拟/正式账户事实可区分。
- 未安装 Fact Secret 时，托盘不崩溃、不退出、不启用下单。
- 正式账户仍由本机正式授权状态和现有正式策略门禁控制，不因 Host Agent 合并而放开权限。

## 当前限制

- 18666 仍是只读 Shadow；不接收租约、订单或执行意图。
- `.125/.113` 的新 EXE 尚未远程替换，需通过各自主机 Git 分支由 VS Code（Claude）编译部署。
- 独立 `BigQMTHostAgentTray.exe` 暂保留作兼容回滚，不应与账户托盘同时启动。
