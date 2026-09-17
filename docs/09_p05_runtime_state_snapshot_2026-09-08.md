# P05 运行状态库：首个模拟盘快照

时间：2026-09-08 09:52（Asia/Shanghai）  
环境：模拟版国金 QMT；BigQMT Redis RPC；只读。

## 已实现

- 主机侧 `ReadOnlyBigQmtClient`：仅允许 ping、资产、持仓、委托、成交和完整行情快照六类读方法；未实现也不接受下单或撤单方法。
- 无第三方 Python 依赖的 Redis RESP 客户端，连接项目本机 Redis 第 5 库。
- SQLite WAL 运行状态库：快照运行、账户资产、持仓、委托、成交、行情快照与审计事件表。
- JSONL 追加审计文件，按 UTC 日期分目录保存。
- `scripts/run_readonly_snapshot.py`：执行一轮有边界的只读采集；默认对现有持仓逐一取得完整行情快照。

## 验收结果

离线 SQLite 单元测试通过。真实模拟盘执行脚本的结果：

- 总资产快照成功；
- 5 个持仓已写入 SQLite；
- 5 个标的的完整行情快照已写入 SQLite；
- 委托、成交均为 0；
- `rpc_allow_order_methods=False` 继续在 QMT Bridge 服务端生效。

状态库：`runtime_data\\state\\simulation\\qmt_runtime.sqlite3`  
审计目录：`runtime_data\\audit\\simulation\\<UTC 日期>\\readonly_snapshot.jsonl`

## 未完成与下一门禁

这只是一次性快照，不代表连续实时行情或重启恢复已经通过。下一项工作是将快照
采集做成受控轮询任务，记录行情事件时间、接收时间和新鲜度，并验证 Redis/QMT 中断、
恢复与对账；订单方法继续关闭。
