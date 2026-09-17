# Coordinator Dashboard 空白页面修复记录

日期：2026-09-16 22:32（Asia/Shanghai）

## 现象

`http://192.0.2.121:18443/` 与 `http://192.0.2.121:18666/` 的 API 均返回 200，但浏览器页面停留在“正在读取 Coordinator 状态…”。浏览器控制台报：

```text
SyntaxError: missing ) after argument list
```

## 根因与修复

内嵌 Dashboard JavaScript 的 `render()` 中，`title.append(node(...), node(...))` 少了一个右括号。已完成：

- 本地 `scripts/coordinator/serve.py` 修复；
- Shadow 镜像重建为 `kitling-bigqmt-coordinator:shadow-20260916-fix`；
- Shadow 容器强制重建并恢复健康；
- 权威服务先回滚整文件版本差异，再对现有远端版本做单字符级热修复；
- 原文件保留在 `/opt/bigqmt-coordinator/backups/20260916_2145_before_dashboard_js_hotfix/serve.py`。

## 浏览器验证

Playwright 加载两个页面，等待前端刷新后结果：

```text
18443: title=BigQMT Coordinator, hostCount=1, accountCount=2,
       intent=空队列／只读, page errors=[]
18666: title=BigQMT Coordinator, hostCount=0, accountCount=0,
       intent=空队列／只读, page errors=[]
```

`18443` 显示 `.105` 及两个账户；`18666` 显示空主机列表是预期行为，因为托盘心跳仍发送到权威端点，Shadow 未接入生产心跳。

订单、租约、事实写入边界未改变，`orders_enabled=false`。

