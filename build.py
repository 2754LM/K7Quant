"""PyInstaller 打包"""
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
        "--add-data=quant_core;quant_core",
        "--hidden-import=quant_core",
        "--hidden-import=quant_core.config",
        "--hidden-import=quant_core.data.fetcher",
        "--hidden-import=quant_core.backtest",
        "--hidden-import=backend.app",
        "--hidden-import=backend.services.backtest_service",
        "run.py",
    ]
    subprocess.check_call(cmd, cwd=ROOT)
    print(f"\n✅ 完成: {ROOT}\\dist\\K7Quant.exe")


if __name__ == "__main__":
    build_frontend()
    install_pyinstaller()
    build_exe()