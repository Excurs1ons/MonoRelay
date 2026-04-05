#!/usr/bin/env bash
# MonoRelay 前台一键启动脚本 (Bash)
# 用法: ./start.sh
# 已委托给 start.py 统一处理

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查虚拟环境
if [ ! -f ".venv/bin/python" ]; then
    echo "[*] 创建 Python 虚拟环境..."
    python3 -m venv .venv
fi

# 安装依赖
echo "[*] 检查依赖..."
.venv/bin/pip install -q -r requirements.txt

# 委托给 start.py 前台启动
exec .venv/bin/python start.py "$@"
