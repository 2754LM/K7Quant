"""SQLite 存储层: 表初始化 + CRUD 工具"""
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional

from backend.core import DB_PATH
from backend.core.logger import log


# 单例连接
_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        init_schema(_conn)
    return _conn


@contextmanager
def transaction():
    """自动提交/回滚上下文"""
    with _lock:
        conn = get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def init_schema(conn: sqlite3.Connection):
    """初始化所有表"""
    cur = conn.cursor()
    # 币种元信息
    cur.execute("""
        CREATE TABLE IF NOT EXISTS symbols (
            symbol TEXT PRIMARY KEY,
            name_zh TEXT NOT NULL,
            name_en TEXT NOT NULL,
            category TEXT,
            market_cap_rank INTEGER,
            description TEXT,
            tags TEXT,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 策略
    cur.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            code TEXT NOT NULL,
            params_schema TEXT,
            is_builtin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 因子 (元信息)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS factors (
            id TEXT PRIMARY KEY,
            name_zh TEXT NOT NULL,
            name_en TEXT,
            category TEXT,
            formula TEXT,
            params_schema TEXT,
            description TEXT
        )
    """)
    # 因子计算结果 (按查询存)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS factor_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            factor_id TEXT NOT NULL,
            params TEXT,
            result_values TEXT,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, timeframe, factor_id, params)
        )
    """)
    # 自定义规则/查询
    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            rule_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 回测结果
    cur.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id INTEGER,
            strategy_name TEXT,
            params TEXT,
            metrics TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 模拟/实盘交易记录
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            amount REAL NOT NULL,
            pnl REAL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    log.info(f"DB schema ready at {DB_PATH}")


def reset_db():
    """删除所有表 (调试用)"""
    with transaction() as conn:
        for table in ["symbols", "strategies", "factors", "factor_results",
                      "custom_rules", "backtest_runs", "trades"]:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
    global _conn
    _conn = None
    init_schema(get_conn())