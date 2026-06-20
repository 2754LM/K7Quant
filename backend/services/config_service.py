"""配置业务: 读写 settings + symbols + 策略"""
from backend.core import config as sys_config
from backend.storage import crud


def get_full_config() -> dict:
    settings = sys_config.load_config()
    symbols = crud.list_symbols()
    # DB 里已有所有策略 (init_builtin_strategies 启动时已写入), 直接用 DB id 保证一致性
    strategies = crud.list_strategies()
    return {
        "settings": settings,
        "symbols": symbols,
        "strategies": strategies,
    }