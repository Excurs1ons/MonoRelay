# PrismaAPIRelay 后台运行 (PowerShell)
# 用法: .\start-bg.ps1 [start|stop|restart|status]

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PrismaAPIRelay 后台运行" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 检查虚拟环境
if (-not (Test-Path ".venv/Scripts/python.exe")) {
    Write-Host "[*] 创建 Python 虚拟环境..." -ForegroundColor Green
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[x] 虚拟环境创建失败，请检查 Python 是否安装" -ForegroundColor Red
        exit 1
    }
}

# 安装依赖
Write-Host "[*] 检查依赖..." -ForegroundColor Green
.venv/Scripts/python.exe -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[x] 依赖安装失败" -ForegroundColor Red
    exit 1
}

$action = if ($args.Count -gt 0) { $args[0] } else { "start" }
$extraArgs = if ($args.Count -gt 1) { $args[1..($args.Count-1)] } else { @() }

switch ($action.ToLower()) {
    "start" {
        & .venv/Scripts/python.exe start.py --bg @extraArgs
    }
    "stop" {
        & .venv/Scripts/python.exe start.py --stop
    }
    "restart" {
        & .venv/Scripts/python.exe start.py --restart @extraArgs
    }
    "status" {
        & .venv/Scripts/python.exe start.py --status
    }
    default {
        Write-Host ""
        Write-Host "用法: .\start-bg.ps1 [start|stop|restart|status]" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  start   后台启动（默认）" -ForegroundColor White
        Write-Host "  stop    停止后台运行" -ForegroundColor White
        Write-Host "  restart 重启后台服务" -ForegroundColor White
        Write-Host "  status  查看运行状态" -ForegroundColor White
        Write-Host ""
        Write-Host "额外参数传递给 start.py:" -ForegroundColor Gray
        Write-Host "  --port PORT     指定端口（默认 8787）" -ForegroundColor Gray
        Write-Host "  --host HOST     指定绑定地址" -ForegroundColor Gray
        Write-Host "  --log-level LVL 日志级别" -ForegroundColor Gray
        Write-Host "  --config PATH   配置文件路径" -ForegroundColor Gray
    }
}
