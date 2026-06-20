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

rem 强制清理旧的前端构建产物, 避免修改后没生效
if exist frontend\dist (
    echo [清理] 删除旧的 frontend\dist 重新构建...
    rd /s /q frontend\dist
)

if not exist frontend\dist\index.html (
    echo [构建] 首次运行 / 重新构建前端...
    cd frontend
    call npm install --registry https://registry.npmmirror.com
    call npm run build
    cd ..
)

rem 浏览器由 run.py 按 config.yaml 里的端口自动打开 (不再硬编码 8765)
venv\Scripts\python.exe run.py
pause