@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   K7Quant 启动
echo ============================================

cd /d "%~dp0"

if not exist venv\Scripts\python.exe (
    echo [错误] 未找到虚拟环境，请先运行 install.bat
    pause
    exit /b 1
)

rem ===== 1. 杀掉之前残留的 K7Quant 进程 (按端口 8765 找) =====
echo [1/4] 检查并清理残留进程...
set "KILLED=0"

rem 优先按端口找占用进程并结束
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8765 .*LISTENING"') do (
    if not "%%P"=="0" (
        taskkill /F /PID %%P >nul 2>&1
        set "KILLED=1"
    )
)

rem 兜底：杀掉所有 pythonw.exe (启动器使用 pythonw)
for /f "tokens=2 delims=," %%P in ('tasklist /FI "IMAGENAME eq pythonw.exe" /FO CSV /NH 2^>nul') do (
    taskkill /F /PID %%P >nul 2>&1
    set "KILLED=1"
)

if "%KILLED%"=="1" (
    echo       已结束残留进程，等待端口释放...
    timeout /t 2 /nobreak >nul
) else (
    echo       未发现残留进程
)

rem ===== 2. 清理 Python 字节码缓存 (避免使用旧的 .pyc) =====
echo [2/4] 清理 Python 缓存...
for /d /r "%~dp0backend" %%D in (__pycache__) do (
    if exist "%%D" rd /s /q "%%D" >nul 2>&1
)
del /s /q "%~dp0backend\*.pyc" >nul 2>&1
del /s /q "%~dp0backend\**\*.pyc" >nul 2>&1
echo       缓存已清理

rem ===== 3. 强制重新构建前端 (避免用旧 dist) =====
echo [3/4] 重新构建前端 (避免使用旧 dist)...
if exist frontend\dist (
    rd /s /q frontend\dist >nul 2>&1
)
if exist frontend\node_modules\.vite (
    rd /s /q frontend\node_modules\.vite >nul 2>&1
)
if not exist frontend\node_modules (
    echo       [提示] 未检测到 node_modules，正在安装...
    cd /d frontend
    call npm install --registry https://registry.npmmirror.com
    cd /d "%~dp0"
)
cd /d frontend
call npm run build
if errorlevel 1 (
    echo [错误] 前端构建失败，请检查 Node.js 与网络
    pause
    exit /b 1
)
cd /d "%~dp0"

rem ===== 4. 启动后端 =====
echo [4/4] 启动后端 (端口取自 config.yaml)...
echo.
venv\Scripts\pythonw.exe run.py
endlocal