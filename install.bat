@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   K7Quant 安装
echo ============================================

cd /d "%~dp0"

where node >nul 2>&1
if errorlevel 1 (
    echo [错误] 未安装 Node.js，请先安装 Node.js 18+
    pause
    exit /b 1
)

if not exist venv (
    echo [1/3] 创建虚拟环境...
    python -m venv venv
)

echo [2/3] 安装 Python 依赖 (SQLAlchemy + FastAPI + ...)...
venv\Scripts\python.exe -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [3/3] 安装前端依赖并构建 (Naive UI + Vue3 + ECharts)...
cd /d frontend
call npm install --registry https://registry.npmmirror.com
call npm run build
cd /d "%~dp0"

echo.
echo ============================================
echo   安装完成！双击 start.bat 启动
echo   - 后端: http://127.0.0.1:8765
echo   - 前端开发模式: cd frontend ^&^& npm run dev
echo ============================================
endlocal
pause