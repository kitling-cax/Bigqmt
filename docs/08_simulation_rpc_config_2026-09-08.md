# 模拟 BigQMT Redis/RPC 配置

部署位置：`F:\\kitling_QMT_work\\国金QMT交易端模拟\\python\\bigqmt_signal_trader_local_config.py`

该配置只写入模拟版 QMT，连接项目本机 Redis `127.0.0.1:6379` 的第 5 库。

安全约束：

- `rpc_allow_order_methods=False`：远程下单和撤单 RPC 在 Bridge 服务层直接拒绝。
- 仅用于账户、持仓、委托、成交和行情的只读验证。
- 不启用历史下载任务、全行情缓存或成交事件推送。
- 正式 QMT 未创建该文件，未部署 Redis RPC，未授权下单。

配置会在 `BIGQMT_REDIS_DRYRUN` 下一次停止并重新启动时加载。验收标志是
`[bigqmt_rpc] transport=redis ... allow_order_methods=False`、RPC 启动日志，以及
Redis 第 5 库中出现 `bigqmt:*` 请求/响应相关键。 
