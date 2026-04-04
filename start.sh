#!/usr/bin/env bash
# PrismaAPIRelay 一键启动脚本 (Bash)
# 用法: ./start.sh

set -e

PORT=8787

echo "========================================"
echo "  PrismaAPIRelay 启动脚本"
echo "========================================"

# 检查配置文件
if [ ! -f "config.yml" ]; then
    echo "[!] config.yml 不存在，从示例复制..."
    if [ -f "config.yml.example" ]; then
        cp config.yml.example config.yml
        echo "[!] 请编辑 config.yml 填入你的 API 密钥"
    else
        echo "[x] 错误: config.yml.example 不存在"
        exit 1
    fi
fi

# 检查虚拟环境
if [ ! -f ".venv/bin/python" ]; then
    echo "[*] 创建 Python 虚拟环境..."
    python3 -m venv .venv
fi

# 安装依赖
echo "[*] 检查依赖..."
.venv/bin/pip install -q -r requirements.txt

# 杀掉占用端口的旧进程
if command -v lsof &> /dev/null; then
    OLD_PID=$(lsof -ti:$PORT 2>/dev/null || true)
elif command -v fuser &> /dev/null; then
    OLD_PID=$(fuser $PORT/tcp 2>/dev/null || true)
else
    OLD_PID=""
fi

if [ -n "$OLD_PID" ]; then
    echo "[*] 发现旧进程 PID=$OLD_PID 占用端口 $PORT，正在终止..."
    kill -9 $OLD_PID 2>/dev/null || true
    sleep 0.5
    echo "[*] 旧进程已终止"
fi

# 启动服务
echo ""
echo "========================================"
echo "  启动 PrismaAPIRelay"
echo "  访问: http://localhost:$PORT"
echo "  按 Ctrl+C 停止服务"
echo "========================================"
echo ""

.venv/bin/python -m backend.main --port $PORT
