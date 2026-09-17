# `.113` VS Code / Claude：GitHub 接入步骤

在 **Windows PowerShell** 执行：

```powershell
cd E:\kitling_QMT_work
git clone https://github.com/kitling-cax/Bigqmt.git Bigqmt-source
cd .\Bigqmt-source
Copy-Item .\config\hosts\113.machine.local.example.json .\config\machine.local.json
git status
git switch -c host/113/<short-topic>
```

Git 源码目录必须与既有 QMT/运行目录分开；只在 `Bigqmt-source` 构建候选包，验证
后才显式部署到本地运行目录。

`machine.local.json` 仅保留本机目录、端口与 host id，Git 已忽略该文件。不得提交
密码、Fact Secret、授权 Key、SQLite/WAL、运行日志或发布二进制。

编译验证、提交和 PR 流程与 `.125` 相同，但分支固定为 `host/113/<short-topic>`。
`.113` 默认 `STANDBY_READONLY`；本机编译成功不等于获得策略运行或下单授权。
