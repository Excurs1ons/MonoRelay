#!/bin/bash
# MonoRelay 打包脚本 (Bash)
# 用法: bash scripts/build.sh

set -e

echo "=== MonoRelay 打包开始 ==="

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 清理旧构建
rm -rf dist build

# 安装依赖
echo ""
echo "[1/4] 安装依赖..."
pip install -r requirements.txt pyinstaller -q

# 打包
echo ""
echo "[2/4] PyInstaller 打包..."
pyinstaller --clean MonoRelay.spec

# 检查输出
if [ ! -f "dist/MonoRelay" ]; then
    echo "✗ 打包失败: 未找到 MonoRelay"
    exit 1
fi

# 复制必要文件到 dist
echo ""
echo "[3/4] 复制配置文件..."
OUTPUT_DIR="dist/MonoRelay"
mkdir -p "$OUTPUT_DIR"

mv dist/MonoRelay "$OUTPUT_DIR/"

# 复制配置模板
if [ -f "config.yml.example" ]; then
    cp config.yml.example "$OUTPUT_DIR/config.yml.example"
fi
if [ ! -f "$OUTPUT_DIR/config.yml" ]; then
    cp config.yml.example "$OUTPUT_DIR/config.yml"
fi

# 创建 data 目录
mkdir -p "$OUTPUT_DIR/data"

# 创建启动脚本
cat > "$OUTPUT_DIR/启动.sh" << 'EOF'
#!/bin/bash
echo "========================================"
echo "  MonoRelay 启动中..."
echo "========================================"
echo ""
./MonoRelay --host 0.0.0.0 --port 8787
EOF
chmod +x "$OUTPUT_DIR/启动.sh"

# 压缩
echo ""
echo "[4/4] 创建压缩包..."
cd dist
zip -r MonoRelay-Linux.zip MonoRelay/
cd ..

EXE_SIZE=$(du -h "dist/MonoRelay/MonoRelay" | cut -f1)
ZIP_SIZE=$(du -h "dist/MonoRelay-Linux.zip" | cut -f1)

echo ""
echo "=== 打包完成 ==="
echo "  可执行文件: dist/MonoRelay/MonoRelay ($EXE_SIZE)"
echo "  压缩包:     dist/MonoRelay-Linux.zip ($ZIP_SIZE)"
echo "  输出目录:   dist/MonoRelay/"
echo ""
echo "使用方法:"
echo "  1. 解压 MonoRelay-Linux.zip"
echo "  2. 编辑 config.yml 填入 API 密钥"
echo "  3. 运行 ./启动.sh 或 ./MonoRelay"
echo "  4. 浏览器打开 http://localhost:8787"
