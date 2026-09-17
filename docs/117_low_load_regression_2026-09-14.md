# 低负载采样调整回归记录（2026-09-14）

## 结果

在 `C:\BigQMT\work\kitling_bigqmt` 执行：

```text
python -m pytest -q
153 passed, 1 skipped in 79.67s
```

本次变更包含：

- BigQMT Tray 监督计时器保持 15 秒；
- 模拟/正式只读账户与持仓基线改为每小时一次，失败 10 分钟后重试；
- Dashboard 策略与状态刷新改为 15 秒；
- 订单锁、正式账户只读和数据湖发布门禁未改变。

托盘运行验证：模拟配置 PID `31556`；Redis `6379`、Bridge 只读 ping、Dashboard `17890` 均通过；启动后小时快照 `33bc0554b16d44759a7d9f3ee593e43f` 状态 `PASSED`，持仓 6、委托 0、成交 0。

