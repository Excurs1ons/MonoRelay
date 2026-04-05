#!/usr/bin/env bash
# PrismaAPIRelay 后台运行 (Bash)
# 用法: ./start-bg.sh [start|stop|restart|status]

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

ACTION="${1:-start}"

case "$ACTION" in
    start)
        .venv/bin/python start.py --bg "$@"
        ;;
    stop)
        .venv/bin/python start.py --stop
        ;;
    restart)
        .venv/bin/python start.py --restart "$@"
        ;;
    status)
        .venv/bin/python start.py --status
        ;;
    *)
        echo "用法: $0 [start|stop|restart|status]"
        echo ""
        echo "  start   后台启动（默认）"
        echo "  stop    停止后台运行"
        echo "  restart 重启后台服务"
        echo "  status  查看运行状态"
        echo ""
        echo "额外参数传递给 start.py:"
        echo "  --port PORT     指定端口（默认 8787）"
        echo "  --host HOST     指定绑定地址"
        echo "  --log-level LVL 日志级别"
        echo "  --config PATH   配置文件路径"
        ;;
esac
