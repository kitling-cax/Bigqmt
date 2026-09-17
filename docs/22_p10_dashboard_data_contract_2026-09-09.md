# P10：只读 Dashboard 数据契约（2026-09-09）

## 接口

现有 loopback Dashboard 的 `GET /api/status` 继续保持只读，并新增 `strategy_sleeves` 字段。实现位于 `src/kitling_bigqmt/dashboard_status.py`，不会连接 QMT 或 Redis。

返回结构的关键部分：

```json
{
  "read_only": true,
  "orders_enabled": false,
  "order_actions_exposed": false,
  "snapshot": {"run_id": "...", "total_asset": 0, "positions": {}},
  "strategy_sleeves": [
    {
      "summary": {
        "strategy_id": "...",
        "initial_capital": 100000,
        "net_asset_value": 100000,
        "return_rate": 0,
        "positions": [],
        "orders_enabled": false
      },
      "nav_series": [
        {"valuation_run_id": "...", "snapshot_time": "...", "net_asset_value": 100000}
      ]
    }
  ],
  "active_blockers": [],
  "next_gate": "..."
}
```

## 口径与安全边界

- `snapshot` 是 QMT 账户只读事实；`strategy_sleeves` 是本地策略归属统计，两者不混写；
- 已有券商持仓仍按 external baseline 处理，不会被 Dashboard 自动归属给策略；
- NAV 曲线来自 SQLite WAL 的 `sleeve_nav_snapshots`，按策略分别查询；
- 缺少估值价格时，袖套返回 `VALUATION_UNAVAILABLE`，不会用零价格伪造收益；
- Dashboard 没有下单、撤单、确认或执行端点，`orders_enabled=false` 固定由项目状态覆盖。

## 当前实测

模拟状态库返回两个袖套：A NAV 100,000 元、B NAV 1,000,000 元，各有一个初始 NAV 点；34 项自动化测试通过。页面视觉布局暂不扩展，后续只需消费该字段即可增加袖套表格和曲线组件。
