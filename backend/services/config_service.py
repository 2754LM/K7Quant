"""配置业务: 读写 settings + symbols + 预置策略"""
from backend.core import config as sys_config
from backend.storage import crud
from backend.strategy import get_builtin_strategies


def get_full_config() -> dict:
    settings = sys_config.load_config()
    symbols = crud.list_symbols()
    strategies = []
    for s in get_builtin_strategies():
        strategies.append({
            "id": s["name"],  # 临时用 name 当 id (内置没 DB id)
            "name": s["name"],
            "description": s["description"],
            "category": s["category"],
            "params_schema": s.get("params_schema", {}),
            "is_builtin": True,
        })
    # 也加上 DB 里的自定义策略
    for s in crud.list_strategies():
        strategies.append(s)
    return {
        "settings": settings,
        "symbols": symbols,
        "strategies": strategies,
    }