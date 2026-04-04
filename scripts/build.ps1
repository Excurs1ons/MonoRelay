# PrismaAPIRelay 打包脚本 (PowerShell)
# 用法: .\scripts\build.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== PrismaAPIRelay 打包开始 ===" -ForegroundColor Cyan

# 切换到项目根目录
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $ProjectRoot

# 清理旧构建
$DistPath = Join-Path $ProjectRoot "dist"
$BuildPath = Join-Path $ProjectRoot "build"
if (Test-Path $DistPath) { Remove-Item -Recurse -Force $DistPath }
if (Test-Path $BuildPath) { Remove-Item -Recurse -Force $BuildPath }

# 安装依赖
Write-Host "`n[1/4] 安装依赖..." -ForegroundColor Yellow
pip install -r requirements.txt pyinstaller -q

# 打包
Write-Host "`n[2/4] PyInstaller 打包..." -ForegroundColor Yellow
pyinstaller --clean PrismaAPIRelay.spec

# 检查输出
$ExePath = Join-Path $DistPath "PrismaAPIRelay.exe"
if (-not (Test-Path $ExePath)) {
    Write-Host "✗ 打包失败: 未找到 PrismaAPIRelay.exe" -ForegroundColor Red
    exit 1
}

# 复制必要文件到 dist
Write-Host "`n[3/4] 复制配置文件..." -ForegroundColor Yellow
$OutputDir = Join-Path $DistPath "PrismaAPIRelay"
if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir | Out-Null }

# 移动 exe 到子目录
Move-Item -Force $ExePath $OutputDir

# 复制配置模板
if (Test-Path "config.yml.example") {
    Copy-Item "config.yml.example" (Join-Path $OutputDir "config.yml.example")
}
if (-not (Test-Path (Join-Path $OutputDir "config.yml"))) {
    Copy-Item "config.yml.example" (Join-Path $OutputDir "config.yml")
}

# 创建 data 目录
New-Item -ItemType Directory -Force (Join-Path $OutputDir "data") | Out-Null

# 创建启动脚本
$StartScript = @"
@echo off
chcp 65001 >nul
echo ========================================
echo   PrismaAPIRelay 启动中...
echo ========================================
echo.
PrismaAPIRelay.exe --host 0.0.0.0 --port 8787
pause
"@
$StartScript | Out-File -FilePath (Join-Path $OutputDir "启动.bat") -Encoding UTF8

# 压缩
Write-Host "`n[4/4] 创建压缩包..." -ForegroundColor Yellow
$ZipName = "PrismaAPIRelay-Windows.zip"
$ZipPath = Join-Path $DistPath $ZipName
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path $OutputDir -DestinationPath $ZipPath

$ExeSize = (Get-Item $ExePath).Length
$ZipSize = (Get-Item $ZipPath).Length

Write-Host "`n=== 打包完成 ===" -ForegroundColor Green
Write-Host "  可执行文件: $ExePath ($([math]::Round($ExeSize/1MB, 1)) MB)"
Write-Host "  压缩包:     $ZipPath ($([math]::Round($ZipSize/1MB, 1)) MB)"
Write-Host "  输出目录:   $OutputDir"
Write-Host "`n使用方法:" -ForegroundColor Cyan
Write-Host "  1. 解压 PrismaAPIRelay-Windows.zip"
Write-Host "  2. 编辑 config.yml 填入 API 密钥"
Write-Host "  3. 双击 启动.bat 或直接运行 PrismaAPIRelay.exe"
Write-Host "  4. 浏览器打开 http://localhost:8787"
