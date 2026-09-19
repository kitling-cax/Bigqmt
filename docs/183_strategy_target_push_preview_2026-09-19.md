# 183：策略候选目标托盘推送预览（2026-09-19）

## 已完成

策略页面 `/strategies` 现在会同时读取：

- `/api/v1/strategy-candidates`：NAS 私有策略库中的已验签 candidate；
- `/api/v1/hosts`：最近心跳仍有效的 `.105`、`.125`、`.113` 托盘。

每个 candidate 卡片会显示目标托盘复选框。点击“生成推送预览”只调用：

```text
POST /api/v1/strategy-push-preview
```

请求包含 `strategy_id`、`version`、`build_id` 和 `target_host_ids`。Coordinator 会重新校验 candidate 的 MANIFEST、artifact checksum 和安全标志，然后为每个目标返回 `READY_TO_PULL` 或 `HOST_NOT_CONNECTED`。

## 明确的安全边界

当前阶段是 preview-only：

- 不复制策略包；
- 不写 Host Agent outbox；
- 不创建策略 assignment；
- 不创建执行租约；
- 不改变本地托盘策略状态；
- `orders_enabled=false`，正式账户仍只读。

因此，页面可以验证“策略版本是否可推送、目标主机是否在线”，但不会误触发安装或下单。

## 当前实测

`.121:18443` 已部署并重启成功。候选 `S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15 / v1.1.15 / 20260919-r1` 返回：

- `.125`：`READY_TO_PULL`；
- `.113`：`READY_TO_PULL`；
- `.105`：当时无有效心跳，`HOST_NOT_CONNECTED`。

返回中 `assignment_created=false`、`install_started=false`、`lease_created=false`。

## 下一阶段

真正安装需要单独的 Host Agent 拉取协议：Host Agent 从 NAS 私有库下载 candidate，校验 MANIFEST 和 SHA-256，写入本地策略版本目录，并回报安装结果。安装完成后仍须由本机托盘明确启动/停止；Coordinator 只负责发布状态和候选，不能绕过本机授权文件取得下单权限。

同一策略可以安装到多个主机，但同一账户同一时刻只能有一个 `ACTIVE_EXECUTOR`。在真正启用 assignment/lease 前，必须增加审批、幂等键、回滚和审计记录测试。

