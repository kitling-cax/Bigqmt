# `.125` VS Code / Claude：GitHub 接入步骤

在 **Windows PowerShell** 执行，不要在 WSL 或 NAS 共享目录中运行源码：

```powershell
cd E:\kitling_QMT_work
git clone https://github.com/kitling-cax/Bigqmt.git kitling_bigqmt
cd .\kitling_bigqmt
Copy-Item .\config\hosts\125.machine.local.example.json .\config\machine.local.json
git status
git switch -c host/125/<short-topic>
```

然后只在本机编辑 `config/machine.local.json` 的路径、端口与 `host_id`。该文件已
被 Git 忽略，不能提交密码、Secret、授权 Key 或 QMT 运行数据。

本机验证：

```powershell
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_portable_host_bundles.ps1
```

需要部署时，使用该分支构建出的 `.125` 包并保留脱敏测试报告。确认无敏感文件后：

```powershell
git add <changed-source-and-doc-files>
git commit -m "feat: <summary>"
git push -u origin host/125/<short-topic>
```

在 GitHub 创建到 `main` 的 PR。禁止直接推送 `main`，禁止在未获 Coordinator
授权的情况下启用下单或尝试切换执行机。
