"""config/paths.py - 路径常量
统一管理项目里所有需要用到的文件/目录路径。
"""
from pathlib import Path

# __file__ = backend/config/paths.py
# .parent = backend/config
# .parent.parent = backend
# .parent.parent.parent = 项目根目录
ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
CACHE_DIR = DATA_DIR / "cache"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "k7quant.db"
CONFIG_PATH = ROOT / "config.yaml"

# 自动创建 (避免下游 import 时路径不存在)
for d in (DATA_DIR, LOGS_DIR, CACHE_DIR, EXPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)