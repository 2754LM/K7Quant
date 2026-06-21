"""因子业务: 因子查询、计算、相关性、摘要"""
from typing import List

import numpy as np
import pandas as pd

from backend.factor import (
    list_factors as _list_factors,
    compute_factor,
    factor_correlation,
    factor_summary,
    register_custom_factor,
    unregister_custom_factor,
    CATEGORIES,
)
from backend.data.access import get_kline, get_many
from backend.services.helpers import df_dates, to_records


def load_custom_factors_from_db():
    """启动时从 DB 把用户自定义因子加载到 FACTOR_REGISTRY"""
    try:
        from backend.models import list_factors as _db_list
        rows = _db_list()
        loaded = 0
        for r in rows:
            if r.get("is_custom") and r.get("dsl_code"):
                try:
                    register_custom_factor(
                        factor_id=r["id"], name_zh=r["name_zh"], category=r["category"],
                        formula=r.get("formula", ""), params_schema=r.get("params_schema", {}),
                        description=r.get("description", ""), dsl_code=r["dsl_code"],
                    )
                    loaded += 1
                except ValueError:
                    # 已注册, 跳过
                    pass
        if loaded:
            from backend.core.logger import log
            log.info(f"[init] 自定义因子加载: {loaded} 个")
    except Exception as e:
        from backend.core.logger import log
        log.warning(f"[init] 自定义因子加载失败: {e}")


def create_custom_factor(data: dict) -> dict:
    """创建自定义因子: 先编译验证 DSL, 再入库 + 注册到运行时"""
    import json as _json
    from backend.models import create_custom_factor as _db_create
    from backend.strategy import StrategyEngine

    factor_id = data["factor_id"]
    dsl_code = data["dsl_code"].strip()
    name_zh = data["name_zh"].strip()
    category = data.get("category", "自定义类").strip() or "自定义类"
    description = data.get("description", "")
    formula = data.get("formula") or dsl_code.replace("\n", " ")

    # 1. 编译验证 DSL (有数据时实跑, 无数据时只校验语法)
    try:
        from backend.data.access import get_kline
        _df = get_kline("BTCUSDT", "1d", "20240101", "20250101")
        if not _df.empty:
            StrategyEngine.compile(dsl_code, {}, mode="factor")
        else:
            # 退而求其次, 解析语法
            StrategyEngine._parse(dsl_code)
    except Exception as e:
        raise ValueError(f"DSL 语法错误: {e}")

    # 2. 入库
    obj = _db_create(
        factor_id=factor_id, name_zh=name_zh, category=category,
        formula=formula, params_schema={}, description=description,
        dsl_code=dsl_code,
    )

    # 3. 注册到运行时
    register_custom_factor(
        factor_id=factor_id, name_zh=name_zh, category=category,
        formula=formula, params_schema={},
        description=description, dsl_code=dsl_code,
    )

    return obj


def delete_custom_factor(factor_id: str):
    """删除自定义因子"""
    from backend.models import delete_custom_factor as _db_del
    _db_del(factor_id)
    unregister_custom_factor(factor_id)


def list_factors(category: str = None) -> dict:
    factors = _list_factors(category)
    return {
        "categories": CATEGORIES,
        "factors": factors,
    }


def get_factor(factor_id: str) -> dict:
    from backend.factor import FACTOR_REGISTRY
    info = FACTOR_REGISTRY.get(factor_id)
    if not info:
        return {"error": f"未知因子: {factor_id}"}
    return {
        "id": info["id"],
        "name_zh": info["name_zh"],
        "name_en": info["name_en"],
        "category": info["category"],
        "formula": info["formula"],
        "description": info["description"],
        "params_schema": info["params_schema"],
    }


def compute(symbol: str, factor_id: str, params: dict = None,
            timeframe: str = "1d", start: str = "20240101", end: str = "20250601",
            limit: int = 500) -> dict:
    """计算单个币种的某个因子"""
    df = get_kline(symbol, timeframe, start, end)
    if df.empty:
        return {"error": f"无 {symbol} 数据"}
    df = df_dates(df, start, end)

    try:
        result = compute_factor(df, factor_id, params or {})
    except Exception as e:
        return {"error": f"计算失败: {e}"}

    if isinstance(result, pd.DataFrame):
        # 多输出: 返回每列
        for col in result.columns:
            df[f"{factor_id}_{col}"] = result[col]
        # 选指定列
        data_records = to_records(df.tail(limit),
                                   ["date"] + [c for c in df.columns if c.startswith(f"{factor_id}_")])
    else:
        df[factor_id] = result
        data_records = to_records(df.tail(limit), ["date", factor_id])

    summary = factor_summary(df, factor_id, params or {})
    return {
        "symbol": symbol, "factor_id": factor_id,
        "params": params or {},
        "summary": summary,
        "data": data_records,
    }


def compute_many(symbol: str, factor_ids: List[str], params_list: List[dict] = None,
                 timeframe: str = "1d", start: str = "20240101", end: str = "20250601",
                 limit: int = 500) -> dict:
    """一次性算多个因子"""
    df = get_kline(symbol, timeframe, start, end)
    if df.empty:
        return {"error": f"无 {symbol} 数据"}
    df = df_dates(df, start, end)

    series_dict = {}
    for i, fid in enumerate(factor_ids):
        params = (params_list[i] if params_list else None) or {}
        try:
            result = compute_factor(df, fid, params)
            if isinstance(result, pd.DataFrame):
                for col in result.columns:
                    series_dict[f"{fid}_{col}"] = result[col]
            else:
                series_dict[fid] = result
        except Exception as e:
            continue

    if not series_dict:
        return {"error": "所有因子计算失败", "data": []}

    out_df = df[["date"]].copy()
    for name, s in series_dict.items():
        out_df[name] = s

    return {
        "symbol": symbol, "factor_ids": factor_ids,
        "data": to_records(out_df.tail(limit)),
    }


def correlate(symbol: str, factor_ids: List[str], params_list: List[dict] = None,
              period: int = None, timeframe: str = "1d",
              start: str = "20240101", end: str = "20250601") -> dict:
    """因子相关性"""
    df = get_kline(symbol, timeframe, start, end)
    if df.empty:
        return {"error": f"无 {symbol} 数据"}
    df = df_dates(df, start, end)
    return {
        "symbol": symbol,
        "factor_ids": factor_ids,
        **factor_correlation(df, factor_ids, params_list, period),
    }


def rank_factors(symbols: List[str], factor_id: str, params: dict = None,
                 timeframe: str = "1d", start: str = "20240101", end: str = "20250601",
                 top: int = 20) -> dict:
    """跨币种按因子值排名"""
    data = get_many(symbols, timeframe, start, end)
    if not data:
        return {"error": "无数据"}

    rows = []
    for sym, df in data.items():
        if df.empty or len(df) < 30:
            continue
        df = df_dates(df, start, end)
        try:
            result = compute_factor(df, factor_id, params or {})
            if isinstance(result, pd.DataFrame):
                result = result.iloc[:, 0]
            s = result.dropna()
            if s.empty:
                continue
            rows.append({
                "symbol": sym,
                "current": float(s.iloc[-1]),
                "min": float(s.min()),
                "max": float(s.max()),
                "mean": float(s.mean()),
                "rank_pct": float((s.rank(pct=True).iloc[-1])),
            })
        except Exception:
            continue

    rows.sort(key=lambda x: x["current"], reverse=True)
    return {"factor_id": factor_id, "ranking": rows[:top]}