@echo off
chcp 65001 >nul
echo ============================================
echo   K7Quant 启动
echo ============================================

if not exist venv\Scripts\python.exe (
    echo [错误] 未找到虚拟环境，请先运行 install.bat
    pause
    exit /b 1
)

if not exist frontend\dist\index.html (
    echo [提示] 首次运行，构建前端...
    cd frontend
    call npm install --registry https://registry.npmmirror.com
    call npm run build
    cd ..
)

start "" http://127.0.0.1:8765
venv\Scripts\python.exe run.py
pause