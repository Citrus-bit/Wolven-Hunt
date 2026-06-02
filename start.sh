#!/bin/bash
# Wolven Hunt - One-Click Startup Script
# 狼人杀 AI 竞技场 - 一键启动脚本

set -e

echo "🐺 Welcome to Wolven Hunt | 欢迎来到狼人杀 AI 竞技场"
echo ""

# Check prerequisites
echo "📋 Checking prerequisites | 检查环境..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.11+ | 未找到 Python 3，请安装 Python 3.11+"
    echo "   Visit: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Python $PYTHON_VERSION found | 找到 Python $PYTHON_VERSION"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Please install Node.js 20+ | 未找到 Node.js，请安装 Node.js 20+"
    echo "   Visit: https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node --version)
echo "✅ Node.js $NODE_VERSION found | 找到 Node.js $NODE_VERSION"

# Check uv
if ! command -v uv &> /dev/null; then
    echo "❌ uv not found. Installing uv... | 未找到 uv，正在安装..."
    echo ""
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"

    if ! command -v uv &> /dev/null; then
        echo "❌ Failed to install uv. Please install manually | uv 安装失败，请手动安装"
        echo "   Visit: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi

UV_VERSION=$(uv --version)
echo "✅ uv $UV_VERSION found | 找到 uv $UV_VERSION"
echo ""

# Install dependencies
echo "📦 Installing dependencies | 安装依赖..."
echo ""

if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies | 安装 Node.js 依赖..."
    npm install
    echo ""
fi

if [ ! -d ".venv" ]; then
    echo "Installing Python dependencies | 安装 Python 依赖..."
    uv sync --extra dev
    echo ""
fi

echo "✅ Dependencies installed | 依赖安装完成"
echo ""

# Build and start
echo "🚀 Building and starting server | 构建并启动服务器..."
echo ""

make serve-prod &
SERVER_PID=$!

# Wait for server to start
echo "⏳ Waiting for server to start | 等待服务器启动..."
sleep 5

# Check if server is running
if curl -s http://localhost:7002/healthz > /dev/null 2>&1; then
    echo ""
    echo "✅ Server is running! | 服务器已启动！"
    echo ""
    echo "🎮 Open your browser | 打开浏览器："
    echo "   👉 http://localhost:7002"
    echo ""
    echo "Press Ctrl+C to stop the server | 按 Ctrl+C 停止服务器"
    echo ""

    # Try to open browser automatically
    if command -v open &> /dev/null; then
        open http://localhost:7002
    elif command -v xdg-open &> /dev/null; then
        xdg-open http://localhost:7002
    fi

    # Wait for server process
    wait $SERVER_PID
else
    echo ""
    echo "⚠️  Server might not be ready yet | 服务器可能还未就绪"
    echo "   Please wait a moment and visit: http://localhost:7002"
    echo "   请稍等片刻并访问：http://localhost:7002"
    echo ""
    wait $SERVER_PID
fi
