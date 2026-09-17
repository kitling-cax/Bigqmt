# 模拟 510300 买卖往返验证（2026-09-10）

## 卖出结果

用户明确确认后，模拟账户 `90000001` 在确认 T+1 可用数量为 100 股、Bridge 已加载一次性权限后，提交唯一一笔卖单：

- 证券：`510300.SH`（沪深300ETF华泰柏瑞）
- 数量：100 股
- 限价：4.622
- 委托号：`176`
- 成交号：`50032305`
- 成交价：4.622
- 成交金额：462.20
- 手续费：0.13866

随后只读快照确认 `volume=0`、`available=0`、`on_road_volume=0`，委托和成交各 1 条。

原始证据：[one_time_510300_sell_20260910_123424.json](../runtime_data/evidence/simulation/one_time_510300_sell_20260910_123424.json)。

## 安全收尾

- `runtime_control.json` 已恢复 `orders_enabled=false`、`execution_consumer_enabled=false`、`valid_until_epoch=0`。
- 模拟本地 QMT 配置已恢复到卖出前备份，`rpc_allow_order_methods=false`。
- 正式账户 `90000002` 未调用下单/撤单接口。
- 为使 QMT 进程内存中的权限标志同步回 false，需在模拟 QMT 中停止并重新启动一次 `BIGQMT_BRIDGE`；在此之前运行控制文件已阻断任何后续订单。
