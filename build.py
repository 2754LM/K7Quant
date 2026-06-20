"""PyInstaller 打包成单 EXE"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def build_frontend():
    print("[1/3] 构建前端...")
    subprocess.check_call(["npm", "run", "build"],
                          cwd=os.path.join(ROOT, "frontend"), shell=True)


def install_pyinstaller():
    print("[2/3] 安装 PyInstaller...")
    py = os.path.join(ROOT, "venv", "Scripts", "pip.exe")
    subprocess.check_call([py, "install", "pyinstaller",
                          "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", "--quiet"])


def build_exe():
    print("[3/3] 打包 EXE...")
    py = os.path.join(ROOT, "venv", "Scripts", "pyinstaller.exe")
    cmd = [
        py, "--name=K7Quant", "--onefile", "--noconsole",
        "--add-data=frontend/dist;frontend/dist",
        "--add-data=config;config",
        "--add-data=quant_core;quant_core",
        "--hidden-import=quant_core",
        "--hidden-import=quant_core.settings",
        "--hidden-import=quant_core.data.fetcher",
        "--hidden-import=quant_core.data.cache",
        "--hidden-import=quant_core.data.access",
        "--hidden-import=quant_core.strategies",
        "--hidden-import=quant_core.strategies.base",
        "--hidden-import=quant_core.strategies.ma_cross",
        "--hidden-import=quant_core.strategies.momentum_rotation",
        "--hidden-import=quant_core.strategies.rsi",
        "--hidden-import=quant_core.strategies.macd",
        "--hidden-import=quant_core.backtest",
        "--hidden-import=quant_core.backtest.engine",
        "--hidden-import=quant_core.backtest.metrics",
        "--hidden-import=backend.app",
        "--hidden-import=backend.services.backtest_service",
        "--hidden-import=backend.services.data_service",
        "--hidden-import=backend.services.config_service",
        "--hidden-import=backend.services.helpers",
        "--hidden-import=backend.routers.backtest",
        "--hidden-import=backend.routers.data",
        "--hidden-import=backend.routers.config",
        "run.py",
    ]
    subprocess.check_call(cmd, cwd=ROOT)
    print(f"\n完成: {ROOT}\\dist\\K7Quant.exe")


if __name__ == "__main__":
    build_frontend()
    install_pyinstaller()
    build_exe()