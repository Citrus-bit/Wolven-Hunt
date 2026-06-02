@echo off
REM Wolven Hunt - One-Click Startup Script for Windows
REM 狼人杀 AI 竞技场 - Windows 一键启动脚本

echo.
echo 🐺 Welcome to Wolven Hunt ^| 欢迎来到狼人杀 AI 竞技场
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Please install Python 3.11+ ^| 未找到 Python，请安装 Python 3.11+
    echo    Visit: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo ✅ Python %PYTHON_VERSION% found ^| 找到 Python %PYTHON_VERSION%

REM Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js not found. Please install Node.js 20+ ^| 未找到 Node.js，请安装 Node.js 20+
    echo    Visit: https://nodejs.org/
    pause
    exit /b 1
)

for /f %%i in ('node --version') do set NODE_VERSION=%%i
echo ✅ Node.js %NODE_VERSION% found ^| 找到 Node.js %NODE_VERSION%

REM Check uv
uv --version >nul 2>&1
if errorlevel 1 (
    echo ❌ uv not found. Please install uv ^| 未找到 uv，请安装 uv
    echo    Visit: https://docs.astral.sh/uv/getting-started/installation/
    echo    Run: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    pause
    exit /b 1
)

for /f %%i in ('uv --version') do set UV_VERSION=%%i
echo ✅ uv %UV_VERSION% found ^| 找到 uv %UV_VERSION%
echo.

REM Install dependencies
echo 📦 Installing dependencies ^| 安装依赖...
echo.

if not exist "node_modules" (
    echo Installing Node.js dependencies ^| 安装 Node.js 依赖...
    call npm install
    echo.
)

if not exist ".venv" (
    echo Installing Python dependencies ^| 安装 Python 依赖...
    call uv sync --extra dev
    echo.
)

echo ✅ Dependencies installed ^| 依赖安装完成
echo.

REM Build and start
echo 🚀 Building and starting server ^| 构建并启动服务器...
echo.

REM Build frontend
call npm run build

REM Start server
echo.
echo ✅ Starting server ^| 启动服务器...
echo.
echo 🎮 Open your browser ^| 打开浏览器：
echo    👉 http://localhost:7002
echo.
echo Press Ctrl+C to stop the server ^| 按 Ctrl+C 停止服务器
echo.

REM Start the server
start http://localhost:7002
uv run python -m wolven_hunt.cli serve-prod --host 0.0.0.0 --port 7002
