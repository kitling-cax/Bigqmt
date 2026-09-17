# P18.1 Dashboard 真路由验收（2026-09-09）

状态：`PASSED`。本项只修改本机 loopback Dashboard 的展示与导航，不提供订单、撤单、Redis 写入或 QMT 写入端点。

## 已交付

`scripts/run_local_dashboard.py` 已实现模拟环境的六个可刷新、可直达页面：

- `/simulation/overview`
- `/simulation/strategies`
- `/simulation/account`
- `/simulation/orders`
- `/simulation/market`
- `/simulation/audit`

侧边栏会更新 URL；浏览器后退会回到前一视图。所有视图均从本机 `/api/status` 的只读状态投影读取。`510300.SH` 显示为“华泰柏瑞沪深300ETF”。

## 验收证据

浏览器自动化在 2026-09-09 15:03（Asia/Shanghai）验证：

- 六个路由均返回 HTTP 200；
- 每个路由载入与其对应的页面标题；
- 从总览点击“策略袖套”得到 `/simulation/strategies`；浏览器后退回到 `/simulation/overview`；
- 页面没有 `button`，不含任何订单或撤单操作控件；
- 浏览器未记录 JavaScript 页面错误。

## 后续

P18.2 将补齐委托/成交字段的标准化投影与时间字段；P18.3 再增加已归属成交的袖套 NAV 曲线。正式账户仍不接入本阶段页面，直至 P13 的只读事实核对完成。
