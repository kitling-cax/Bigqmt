# 复权因子范围接口修复（2026-09-12）

## 问题

BigQMT 某些版本的 `get_divid_factors(code, start, end)` 返回 pandas DataFrame。旧适配器使用 `if answer:` 判断是否有结果，pandas 会抛出：

```text
ValueError: The truth value of a DataFrame is ambiguous
```

这会导致范围查询退回展开路径，甚至把已有因子误判为空。

## 修复

在以下两个源码位置增加了 DataFrame/字典/序列兼容的非空判断，并保留 DataFrame 原始形状交给 RPC serializer 编码；单日展开路径也增加了 DataFrame records 的安全合并：

- `staging/qmt_bridge_simulation/bigqmt_signal_trader/adapters/market_bigqmt.py`
- `C:\BigQMT\work\xtquant_big_convert\src\bigqmt_signal_trader\adapters\market_bigqmt.py`

没有修改用户正在运行的 QMT `BIGQMT_BRIDGE` 策略文件，也没有自动重新部署或触发交易。

## 验证

- `xtquant_big_convert` 因子范围测试：18 passed。
- 本项目回归测试：72 passed。
- 源码编译检查：通过。

这项修复为后续 PIT 因子同步扫清了适配器错误，但正式 PIT 发布仍需在 QMT 端重新加载包含修复的 Bridge 版本后，再验证真实因子 payload 和 `available_at`。
