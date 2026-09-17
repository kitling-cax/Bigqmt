# P19 可移植部署首个自检工具

新增只读命令：

```powershell
py scripts\check_portable_deployment.py --profile simulation
py scripts\check_portable_deployment.py --profile production_readonly
```

在另一台电脑复制项目、调整 `config/tray_profiles.json` 与两个 gateway 配置后，先运行上述命令。它不会启动 QMT、Redis、Bridge 或 Dashboard，不会连接券商，也不会修改任何文件。

检查范围：项目与托盘启动文件、QMT 根目录及 `python` 目录、profile Redis 参数一致性、状态库目录、正式盘 `read_only=true`、以及两个 profile 的 `orders_enabled=false`。

本机模拟和正式只读 profile 均已通过。发布清单已把该自检脚本与模块纳入，以便复制校验。
