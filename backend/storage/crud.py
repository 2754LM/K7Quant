"""CRUD: 币种、策略、因子、规则、回测、交易"""
import json
import sqlite3
from typing import Optional
from datetime import datetime

from backend.storage.db import get_conn, transaction


# ============ 币种 ============

def upsert_symbol(symbol: str, name_zh: str, name_en: str, category: str,
                  market_cap_rank: int, description: str, tags: list, is_active: int = 0):
    with transaction() as conn:
        conn.execute("""
            INSERT INTO symbols (symbol, name_zh, name_en, category, market_cap_rank, description, tags, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name_zh=excluded.name_zh, name_en=excluded.name_en,
                category=excluded.category, market_cap_rank=excluded.market_cap_rank,
                description=excluded.description, tags=excluded.tags,
                is_active=excluded.is_active
        """, (symbol, name_zh, name_en, category, market_cap_rank, description,
              json.dumps(tags, ensure_ascii=False), is_active))


def get_symbol(symbol: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM symbols WHERE symbol=?", (symbol,)
    ).fetchone()
    return dict(row) if row else None


def list_symbols(active_only: bool = False) -> list:
    if active_only:
        rows = get_conn().execute(
            "SELECT * FROM symbols WHERE is_active=1 ORDER BY market_cap_rank"
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM symbols ORDER BY market_cap_rank"
        ).fetchall()
    return [_row_to_symbol(r) for r in rows]


def _row_to_symbol(row) -> dict:
    d = dict(row)
    if d.get("tags"):
        try:
            d["tags"] = json.loads(d["tags"])
        except Exception:
            d["tags"] = []
    d["is_active"] = bool(d.get("is_active", 0))
    return d


def set_active_symbols(symbols: list):
    with transaction() as conn:
        conn.execute("UPDATE symbols SET is_active=0")
        for s in symbols:
            conn.execute("UPDATE symbols SET is_active=1 WHERE symbol=?", (s,))


# ============ 策略 ============

def create_strategy(name: str, description: str, category: str, code: str,
                    params_schema: dict, is_builtin: int = 0) -> int:
    with transaction() as conn:
        cur = conn.execute("""
            INSERT INTO strategies (name, description, category, code, params_schema, is_builtin)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, description, category, code,
              json.dumps(params_schema, ensure_ascii=False), is_builtin))
        return cur.lastrowid


def update_strategy(strategy_id: int, name: str, description: str, category: str,
                    code: str, params_schema: dict):
    with transaction() as conn:
        conn.execute("""
            UPDATE strategies SET name=?, description=?, category=?, code=?,
                params_schema=?, updated_at=CURRENT_TIMESTAMP WHERE id=?
        """, (name, description, category, code,
              json.dumps(params_schema, ensure_ascii=False), strategy_id))


def delete_strategy(strategy_id: int):
    with transaction() as conn:
        conn.execute("DELETE FROM strategies WHERE id=? AND is_builtin=0", (strategy_id,))


def get_strategy(strategy_id: int) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM strategies WHERE id=?", (strategy_id,)
    ).fetchone()
    return _row_to_strategy(row) if row else None


def list_strategies() -> list:
    rows = get_conn().execute(
        "SELECT * FROM strategies ORDER BY is_builtin DESC, id"
    ).fetchall()
    return [_row_to_strategy(r) for r in rows]


def _row_to_strategy(row) -> dict:
    d = dict(row)
    for k in ("params_schema",):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                d[k] = {}
    d["is_builtin"] = bool(d.get("is_builtin", 0))
    return d


# ============ 因子 ============

def upsert_factor(factor_id: str, name_zh: str, name_en: str, category: str,
                  formula: str, params_schema: dict, description: str):
    with transaction() as conn:
        conn.execute("""
            INSERT INTO factors (id, name_zh, name_en, category, formula, params_schema, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name_zh=excluded.name_zh, name_en=excluded.name_en,
                category=excluded.category, formula=excluded.formula,
                params_schema=excluded.params_schema, description=excluded.description
        """, (factor_id, name_zh, name_en, category, formula,
              json.dumps(params_schema, ensure_ascii=False), description))


def get_factor(factor_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM factors WHERE id=?", (factor_id,)
    ).fetchone()
    return _row_to_factor(row) if row else None


def list_factors(category: str = None) -> list:
    if category:
        rows = get_conn().execute(
            "SELECT * FROM factors WHERE category=? ORDER BY id", (category,)
        ).fetchall()
    else:
        rows = get_conn().execute("SELECT * FROM factors ORDER BY id").fetchall()
    return [_row_to_factor(r) for r in rows]


def _row_to_factor(row) -> dict:
    d = dict(row)
    if d.get("params_schema"):
        try:
            d["params_schema"] = json.loads(d["params_schema"])
        except Exception:
            d["params_schema"] = {}
    return d


# ============ 自定义规则 ============

def create_rule(name: str, description: str, rule_json: dict) -> int:
    with transaction() as conn:
        cur = conn.execute("""
            INSERT INTO custom_rules (name, description, rule_json)
            VALUES (?, ?, ?)
        """, (name, description, json.dumps(rule_json, ensure_ascii=False)))
        return cur.lastrowid


def list_rules() -> list:
    rows = get_conn().execute(
        "SELECT * FROM custom_rules ORDER BY id DESC"
    ).fetchall()
    return [_row_to_rule(r) for r in rows]


def delete_rule(rule_id: int):
    with transaction() as conn:
        conn.execute("DELETE FROM custom_rules WHERE id=?", (rule_id,))


def _row_to_rule(row) -> dict:
    d = dict(row)
    if d.get("rule_json"):
        try:
            d["rule_json"] = json.loads(d["rule_json"])
        except Exception:
            pass
    return d


# ============ 回测结果 ============

def save_backtest_run(strategy_name: str, params: dict, metrics: dict) -> int:
    with transaction() as conn:
        cur = conn.execute("""
            INSERT INTO backtest_runs (strategy_name, params, metrics)
            VALUES (?, ?, ?)
        """, (strategy_name, json.dumps(params, ensure_ascii=False),
              json.dumps(metrics, ensure_ascii=False)))
        return cur.lastrowid


def list_backtest_runs(limit: int = 50) -> list:
    rows = get_conn().execute(
        "SELECT * FROM backtest_runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("params", "metrics"):
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except Exception:
                    pass
        out.append(d)
    return out


# ============ 交易记录 ============

def insert_trade(mode: str, symbol: str, side: str, price: float,
                 amount: float, pnl: float = 0, note: str = ""):
    with transaction() as conn:
        conn.execute("""
            INSERT INTO trades (mode, symbol, side, price, amount, pnl, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (mode, symbol, side, price, amount, pnl, note))


def list_trades(mode: str = None, limit: int = 100) -> list:
    if mode:
        rows = get_conn().execute(
            "SELECT * FROM trades WHERE mode=? ORDER BY id DESC LIMIT ?",
            (mode, limit)
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]