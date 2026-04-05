# PrismaAPIRelay 前台一键启动脚本 (PowerShell)
# 用法: 右键 "使用 PowerShell 运行" 或在终端执行 .\start.ps1
# 已委托给 start.py 统一处理

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

try {
    # 检查虚拟环境
    if (-not (Test-Path ".venv/Scripts/python.exe")) {
        Write-Host "[*] 创建 Python 虚拟环境..." -ForegroundColor Green
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[x] 虚拟环境创建失败，请检查 Python 是否安装" -ForegroundColor Red
            Read-Host "按回车键退出"
            exit 1
        }
    }

    # 安装依赖
    Write-Host "[*] 检查依赖..." -ForegroundColor Green
    .venv/Scripts/python.exe -m pip install -q -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[x] 依赖安装失败" -ForegroundColor Red
        Read-Host "按回车键退出"
        exit 1
    }

    # 委托给 start.py 前台启动
    & .venv/Scripts/python.exe start.py @args
}
catch {
    Write-Host ""
    Write-Host "[x] 发生错误: $_" -ForegroundColor Red
    Write-Host ""
    Read-Host "按回车键退出"
    exit 1
}
