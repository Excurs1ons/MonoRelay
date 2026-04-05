"""PrismaAPIRelay 跨平台统一启动脚本。

功能：
  - 自动创建虚拟环境、安装依赖
  - 支持前台 / 后台运行
  - 支持 kill 后台进程
  - 支持状态查询

用法：
  python start.py              # 前台启动
  python start.py --bg          # 后台启动
  python start.py --status      # 查看运行状态
  python start.py --stop        # 停止后台运行
  python start.py --restart     # 重启（先停再后台启动）

  可选参数：
  --port PORT                   # 指定端口（默认 8787）
  --host HOST                   # 指定绑定地址（默认 0.0.0.0）
  --log-level LEVEL             # 日志级别（默认 INFO）
  --config PATH                 # 配置文件路径（默认 config.yml）
"""
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
PID_FILE = PROJECT_ROOT / "data" / ".server.pid"
LOG_FILE = PROJECT_ROOT / "data" / "server.log"
DEFAULT_PORT = 8787
DEFAULT_HOST = "0.0.0.0"

# ── 辅助函数 ──────────────────────────────────────────────────────────


def banner(title: str) -> None:
    width = 40
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def venv_python() -> Path:
    if platform.system() == "Windows":
        return PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    return PROJECT_ROOT / ".venv" / "bin" / "python"


def ensure_venv() -> None:
    py = venv_python()
    if py.exists():
        return
    print("[*] 创建 Python 虚拟环境...")
    subprocess.run([sys.executable, "-m", "venv", str(PROJECT_ROOT / ".venv")], check=True)
    print("[*] 虚拟环境创建完成")


def ensure_deps() -> None:
    py = venv_python()
    req = PROJECT_ROOT / "requirements.txt"
    if not req.exists():
        print("[!] requirements.txt 不存在，跳过依赖安装")
        return
    print("[*] 检查依赖...")
    subprocess.run(
        [str(py), "-m", "pip", "install", "-q", "-r", str(req)],
        check=True,
    )


def ensure_config() -> None:
    cfg = PROJECT_ROOT / "config.yml"
    if cfg.exists():
        return
    example = PROJECT_ROOT / "config.yml.example"
    if not example.exists():
        print("[x] 错误: config.yml 和 config.yml.example 都不存在")
        sys.exit(1)
    print("[!] config.yml 不存在，从示例复制...")
    import shutil
    shutil.copy2(str(example), str(cfg))
    print("[!] 请编辑 config.yml 填入你的 API 密钥")


def kill_port(port: int) -> None:
    system = platform.system()
    old_pid: str | None = None

    if system == "Windows":
        # netstat -ano | findstr :PORT.*LISTENING
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    old_pid = parts[-1]
                    break
        except Exception:
            pass
    else:
        # Linux/macOS: lsof or fuser
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5,
            )
            old_pid = result.stdout.strip() or None
        except FileNotFoundError:
            try:
                result = subprocess.run(
                    ["fuser", f"{port}/tcp"],
                    capture_output=True, text=True, timeout=5,
                )
                old_pid = result.stdout.strip() or None
            except FileNotFoundError:
                pass

    if old_pid:
        print(f"[*] 发现旧进程 PID={old_pid} 占用端口 {port}，正在终止...")
        try:
            if system == "Windows":
                subprocess.run(["taskkill", "/F", "/PID", old_pid],
                               capture_output=True, timeout=5)
            else:
                subprocess.run(["kill", "-9", old_pid],
                               capture_output=True, timeout=5)
            time.sleep(0.5)
            print("[*] 旧进程已终止")
        except Exception:
            print("[!] 无法终止旧进程，继续启动")


def write_pid(pid: int) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid), encoding="utf-8")


def read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        # 检查进程是否存活
        if platform.system() == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5,
            )
            if str(pid) not in result.stdout:
                PID_FILE.unlink(missing_ok=True)
                return None
        else:
            os.kill(pid, 0)  # 仅检查，不发送信号
    except (ValueError, ProcessLookupError, OSError):
        PID_FILE.unlink(missing_ok=True)
        return None
    return pid


def print_status() -> None:
    pid = read_pid()
    if pid:
        banner("PrismaAPIRelay 运行中")
        print(f"  PID:  {pid}")
        print(f"  日志: {LOG_FILE}")
        print(f"  PID文件: {PID_FILE}")
    else:
        banner("PrismaAPIRelay 未运行")


def stop_server() -> bool:
    pid = read_pid()
    if not pid:
        print("[!] 服务器未在后台运行")
        return False

    print(f"[*] 正在停止 PID={pid}...")
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=5)
        else:
            subprocess.run(["kill", str(pid)], capture_output=True, timeout=5)
        # 等待进程退出
        for _ in range(10):
            if read_pid() is None:
                print("[*] 服务器已停止")
                return True
            time.sleep(0.3)
        # 强制 kill
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=5)
        else:
            subprocess.run(["kill", "-9", str(pid)], capture_output=True, timeout=5)
        PID_FILE.unlink(missing_ok=True)
        print("[*] 服务器已强制停止")
        return True
    except Exception as e:
        print(f"[x] 停止失败: {e}")
        return False


# ── 核心启动 ──────────────────────────────────────────────────────────


def start_foreground(args: argparse.Namespace) -> None:
    banner("PrismaAPIRelay 启动脚本")

    ensure_config()
    ensure_venv()
    ensure_deps()
    kill_port(args.port)

    print()
    banner(f"启动 PrismaAPIRelay — http://localhost:{args.port}")
    print("  按 Ctrl+C 停止服务\n")

    py = venv_python()
    cmd = [
        str(py), "-m", "backend.main",
        "--port", str(args.port),
        "--host", args.host,
        "--log-level", args.log_level,
    ]
    if args.config:
        cmd += ["--config", args.config]

    os.chdir(str(PROJECT_ROOT))
    os.execv(str(py), cmd)  # 替换当前进程，不产生额外子进程


def start_background(args: argparse.Namespace) -> None:
    banner("PrismaAPIRelay 后台启动")

    # 检查是否已在运行
    pid = read_pid()
    if pid:
        print(f"[!] 服务器已在后台运行 (PID={pid})")
        print("    使用 python start.py --stop 停止")
        print("    使用 python start.py --restart 重启")
        return

    ensure_config()
    ensure_venv()
    ensure_deps()
    kill_port(args.port)

    py = venv_python()
    cmd = [
        str(py), "-m", "backend.main",
        "--port", str(args.port),
        "--host", args.host,
        "--log-level", args.log_level,
    ]
    if args.config:
        cmd += ["--config", args.config]

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    print(f"[*] 启动后台服务...")
    with open(str(LOG_FILE), "a", encoding="utf-8") as log_f:
        proc = subprocess.Popen(
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
        )

    write_pid(proc.pid)
    print(f"[*] 服务已启动 (PID={proc.pid})")
    print(f"[*] 访问: http://localhost:{args.port}")
    print(f"[*] 日志: {LOG_FILE}")
    print(f"[*] 停止: python start.py --stop")


# ── 入口 ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PrismaAPIRelay 跨平台统一启动脚本",
    )
    parser.add_argument("--bg", action="store_true", help="后台运行")
    parser.add_argument("--stop", action="store_true", help="停止后台运行")
    parser.add_argument("--status", action="store_true", help="查看运行状态")
    parser.add_argument("--restart", action="store_true", help="重启后台服务")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="绑定地址")
    parser.add_argument("--log-level", type=str, default="INFO", help="日志级别")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")

    args = parser.parse_args()

    if args.status:
        print_status()
        return

    if args.stop:
        stop_server()
        return

    if args.restart:
        stop_server()
        time.sleep(0.5)
        start_background(args)
        return

    if args.bg:
        start_background(args)
    else:
        start_foreground(args)


if __name__ == "__main__":
    main()
