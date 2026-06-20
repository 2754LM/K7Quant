"""配置业务层: 读写 settings + symbols"""
from pathlib import Path

from quant_core.settings import (
    load_settings, update_settings, load_symbols, save_symbols,
)
from quant_core.strategies import ALL_STRATEGIES


def get_full_config() -> dict:
    s = load_settings(reload=True)
    return {
        "settings": s,
        "symbols": load_symbols(reload=True)["symbols"],
        "strategies": [{
            "id": st.id, "name": st.name, "icon": st.icon,
            "description": st.description, "category": st.category,
            "params_schema": st.params_schema,
        } for st in ALL_STRATEGIES],
    }


def update_active_symbols(symbols: list) -> dict:
    """返回新的完整 settings"""
    return update_settings({"active_symbols": symbols})


def update_strategy_defaults(strategy: str, params: dict) -> dict:
    return update_settings({f"strategy_defaults.{strategy}": params})


def update_timeframes(timeframes: list) -> dict:
    return update_settings({"timeframes": timeframes})


def reset_settings():
    """重置为默认配置"""
    from quant_core.settings import SETTINGS_PATH
    if SETTINGS_PATH.exists():
        SETTINGS_PATH.unlink()
    return load_settings(reload=True)