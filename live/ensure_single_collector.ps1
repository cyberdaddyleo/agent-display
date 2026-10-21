# ensure_single_collector.ps1 — 计划任务启动前的单体互斥清理
# 背景：Task Scheduler 停止任务时只杀 cmd.exe 包装进程，python 孙进程可能残留；
#       若直接再启动会变成两个 --loop 实例同时写 live.json / 各开一条 SG 常驻会话。
# 做法：只杀命令行含 collect_live.py 的 python.exe（不含当前 PowerShell 自身）。
$ErrorActionPreference = "SilentlyContinue"
$targets = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*collect_live.py*" }
foreach ($proc in $targets) {
    Write-Host ("kill stale collector pid=" + $proc.ProcessId)
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
}
