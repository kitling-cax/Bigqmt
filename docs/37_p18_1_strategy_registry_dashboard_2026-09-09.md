# P18.1 Dashboard 策略池登记展示证据（2026-09-09）

## 结论

模拟 Dashboard 已将 `config/strategy_registry.json` 的登记结果接入“策略袖套”专门页面，当前展示 2 条登记记录：

1. `S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15`：v1.1.15、ETF、10 万模拟额度、`SIMULATION_ONLY`。
2. `ETF_MOMENTUM_B_SIM_MAIN_V1_1_15`：ETF、100 万模拟额度、`SHADOW_ONLY`，标的池和信号契约仍待复核。

## 安全边界

- 页面仍为只读，`read_only=true`、`orders_enabled=false`、`order_actions_exposed=false`。
- 策略登记只用于身份、资金袖套、来源和信号契约展示，不会自动发布信号，也不会启用下单。
- 正式账户 `90000002` 不在任何登记策略的允许账户中，仍保持只读。
- 模拟账户 510300 的当日买入测试保持 T+1 待处理，不在本次验证中卖出或新增委托。

## 验证结果

- `GET http://127.0.0.1:17890/api/status`：策略登记数量 2；只读为 true；下单开关为 false。
- Dashboard 页面服务已重启以加载最新前端源码，监听端口仍为 17890。
- `py -m pytest -q`：42 passed。
- `py scripts/validate_strategy_registry.py`：`valid=true`，`strategy_count=2`，`errors=[]`。

## 下一步

先完成策略 B 的来源、标的池和信号契约复核，再进入 P23 数据湖定时同步与留存；在此之前不把任何登记策略切换为可执行状态。
