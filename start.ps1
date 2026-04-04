# PrismaAPIRelay 一键启动脚本 (PowerShell)
# 用法: 右键 "使用 PowerShell 运行" 或在终端执行 .\start.ps1

$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PrismaAPIRelay 启动脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

try {
    # 检查配置文件
    if (-not (Test-Path "config.yml")) {
        Write-Host "[!] config.yml 不存在，从示例复制..." -ForegroundColor Yellow
        if (Test-Path "config.yml.example") {
            Copy-Item "config.yml.example" "config.yml"
            Write-Host "[!] 请编辑 config.yml 填入你的 API 密钥" -ForegroundColor Yellow
        } else {
            Write-Host "[x] 错误: config.yml.example 不存在" -ForegroundColor Red
            Read-Host "按回车键退出"
            exit 1
        }
    }

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

    # 杀掉占用 8787 端口的旧进程
    $port = 8787
    $conn = netstat -ano | Select-String ":$port.*LISTENING"
    if ($conn) {
        $oldPid = ($conn -split '\s+')[-1]
        Write-Host "[*] 发现旧进程 PID=$oldPid 占用端口 $port，正在终止..." -ForegroundColor Yellow
        Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
        Write-Host "[*] 旧进程已终止" -ForegroundColor Green
    }

    # 启动服务
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  启动 PrismaAPIRelay" -ForegroundColor Cyan
    Write-Host "  访问: http://localhost:$port" -ForegroundColor Cyan
    Write-Host "  按 Ctrl+C 停止服务" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    .venv/Scripts/python.exe -m backend.main --port $port
}
catch {
    Write-Host ""
    Write-Host "[x] 发生错误: $_" -ForegroundColor Red
    Write-Host ""
    Read-Host "按回车键退出"
    exit 1
}
