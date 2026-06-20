"""核心模块: 路径、日志、配置加载器、DB"""
from pathlib import Path

# 路径常量 (顶层模块级避免循环 import)
# __file__ = backend/core/__init__.py
# .parent = backend/core
# .parent.parent = backend
# .parent.parent.parent = 项目根目录
ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
CACHE_DIR = DATA_DIR / "cache"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "k7quant.db"

for d in [DATA_DIR, LOGS_DIR, CACHE_DIR, EXPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)