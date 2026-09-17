# P14 托盘发布清单（2026-09-09）

托盘已生成首个可复制验证的只读发布清单：

`dist/kitling-bigqmt-tray-20260909-rc1/manifest.json`

清单固定记录 8 个运行文件的相对路径、字节数和 SHA-256，并明确：

- profiles：`simulation`、`production_readonly`；
- `orders_enabled=false`；
- `execution_consumer_enabled=false`；
- `auto_login=false`。

在其他 QMT 电脑部署时，复制项目后运行：

```powershell
py scripts\build_tray_manifest.py
```

再对比 `manifest.json` 的文件哈希。当前仍使用 `.cmd + .ps1`，待 P14 稳定后再制作可选 `.exe` 外壳；不把自动登录和订单权限混入打包流程。

本阶段验证：40 项 Python 测试通过、PowerShell 语法通过、两个 profile 托盘进程持续运行。
