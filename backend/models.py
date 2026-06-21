"""SQLAlchemy ORM 模型 + 数据库连接 (单文件集中维护, 便于扩展)

替换旧的 hand-written sqlite3 + 手写 CRUD, 用 ORM 自动建表/查询/序列化。
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List, Generator, Any

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, Index, select,
)
from sqlalchemy.orm import (
    declarative_base, sessionmaker, scoped_session, Session,
    Mapped, mapped_column, relationship,
)
from sqlalchemy.engine import Engine

from backend.core import DB_PATH
from backend.core.logger import log


Base = declarative_base()


# ============ 实体模型 ============

class Symbol(Base):
    """币种元信息 + 活跃池标记"""
    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    name_zh: Mapped[str] = mapped_column(String(64), nullable=False)
    name_en: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(32))
    market_cap_rank: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[str]] = mapped_column(Text)   # JSON array
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name_zh": self.name_zh,
            "name_en": self.name_en,
            "category": self.category,
            "market_cap_rank": self.market_cap_rank,
            "description": self.description,
            "tags": json.loads(self.tags) if self.tags else [],
            "is_active": bool(self.is_active),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Strategy(Base):
    """策略: 内置或用户自定义"""
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="custom")
    code: Mapped[str] = mapped_column(Text, nullable=False)
    params_schema: Mapped[Optional[str]] = mapped_column(Text)   # JSON
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "category": self.category,
            "code": self.code,
            "params_schema": json.loads(self.params_schema) if self.params_schema else {},
            "is_builtin": bool(self.is_builtin),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Factor(Base):
    """因子元信息 (内置 + 用户自定义 DSL 因子)"""
    __tablename__ = "factors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name_zh: Mapped[str] = mapped_column(String(64), nullable=False)
    name_en: Mapped[Optional[str]] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    formula: Mapped[Optional[str]] = mapped_column(Text)
    params_schema: Mapped[Optional[str]] = mapped_column(Text)   # JSON
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    dsl_code: Mapped[Optional[str]] = mapped_column(Text)       # 用户 DSL 表达式
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name_zh": self.name_zh,
            "name_en": self.name_en or "",
            "category": self.category,
            "formula": self.formula or "",
            "params_schema": json.loads(self.params_schema) if self.params_schema else {},
            "description": self.description or "",
            "is_custom": bool(self.is_custom),
            "dsl_code": self.dsl_code or "",
        }


class CustomRule(Base):
    """用户自定义查询/规则"""
    __tablename__ = "custom_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    rule_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "rule_json": json.loads(self.rule_json) if self.rule_json else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BacktestRun(Base):
    """回测历史记录"""
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(128))
    params: Mapped[Optional[str]] = mapped_column(Text)   # JSON
    metrics: Mapped[Optional[str]] = mapped_column(Text)   # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "params": json.loads(self.params) if self.params else {},
            "metrics": json.loads(self.metrics) if self.metrics else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Trade(Base):
    """模拟/实盘交易记录"""
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)   # simulation / live
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)    # buy / sell
    price: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mode": self.mode,
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "amount": self.amount,
            "pnl": self.pnl,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============ 引擎与会话 ============

_engine: Optional[Engine] = None
_SessionLocal: Optional[scoped_session] = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(
            f"sqlite:///{DB_PATH}",
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        # WAL 模式 + 外键 (通过事件监听)
        from sqlalchemy import event
        @event.listens_for(_engine, "connect")
        def _set_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()
        # 启动时建表
        Base.metadata.create_all(_engine)
        log.info(f"DB engine ready at {DB_PATH}")
        _SessionLocal = scoped_session(
            sessionmaker(bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False)
        )
    return _engine


def get_session() -> Session:
    """获取线程局部的 ORM Session"""
    get_engine()
    return _SessionLocal()


@contextmanager
def transaction() -> Generator[Session, None, None]:
    """事务上下文: 自动 commit / rollback"""
    sess = get_session()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


# ============ Repository (取代手写 crud.py) ============

class Repository:
    """通用 CRUD 包装, 大多数场景够用。特殊查询可以继承或写 custom 方法"""

    @staticmethod
    def all(model, **filters) -> List[Any]:
        with transaction() as s:
            q = s.query(model)
            for k, v in filters.items():
                q = q.filter(getattr(model, k) == v)
            return q.all()

    @staticmethod
    def get(model, pk) -> Optional[Any]:
        with transaction() as s:
            return s.get(model, pk)

    @staticmethod
    def add(model_obj) -> int:
        with transaction() as s:
            s.add(model_obj)
            s.flush()
            return getattr(model_obj, "id", None) or model_obj.id

    @staticmethod
    def delete(model_obj_or_query):
        with transaction() as s:
            if hasattr(model_obj_or_query, "__iter__"):
                for obj in model_obj_or_query:
                    s.delete(obj)
            else:
                s.delete(model_obj_or_query)


# 业务级便捷函数 (保留旧 API 兼容)
def list_symbols(active_only: bool = False) -> list:
    with transaction() as s:
        q = s.query(Symbol).order_by(Symbol.market_cap_rank)
        if active_only:
            q = q.filter(Symbol.is_active == True)  # noqa
        return [r.to_dict() for r in q.all()]


def get_symbol(symbol: str) -> Optional[dict]:
    with transaction() as s:
        obj = s.get(Symbol, symbol)
        return obj.to_dict() if obj else None


def upsert_symbol(symbol: str, name_zh: str, name_en: str, category: str,
                  market_cap_rank: int, description: str, tags: list, is_active: int = 0):
    with transaction() as s:
        obj = s.get(Symbol, symbol)
        if obj is None:
            obj = Symbol(symbol=symbol)
            s.add(obj)
        obj.name_zh = name_zh
        obj.name_en = name_en
        obj.category = category
        obj.market_cap_rank = market_cap_rank
        obj.description = description
        obj.tags = json.dumps(tags or [], ensure_ascii=False)
        obj.is_active = bool(is_active)


def set_active_symbols(symbols: list):
    with transaction() as s:
        s.query(Symbol).update({Symbol.is_active: False})
        if symbols:
            s.query(Symbol).filter(Symbol.symbol.in_(symbols)).update(
                {Symbol.is_active: True}, synchronize_session=False
            )


def list_strategies() -> list:
    with transaction() as s:
        return [r.to_dict() for r in s.query(Strategy)
                .order_by(Strategy.is_builtin.desc(), Strategy.id).all()]


def get_strategy(strategy_id: int) -> Optional[dict]:
    with transaction() as s:
        obj = s.get(Strategy, strategy_id)
        return obj.to_dict() if obj else None


def create_strategy(name: str, description: str, category: str, code: str,
                     params_schema: dict, is_builtin: int = 0) -> int:
    with transaction() as s:
        obj = Strategy(
            name=name, description=description, category=category, code=code,
            params_schema=json.dumps(params_schema or {}, ensure_ascii=False),
            is_builtin=bool(is_builtin),
        )
        s.add(obj)
        s.flush()
        return obj.id


def update_strategy(strategy_id: int, name: str = None, description: str = None,
                     category: str = None, code: str = None, params_schema: dict = None):
    """部分更新: 传入 None 的字段保持原值"""
    with transaction() as s:
        obj = s.get(Strategy, strategy_id)
        if obj is None:
            return
        if name is not None: obj.name = name
        if description is not None: obj.description = description
        if category is not None: obj.category = category
        if code is not None: obj.code = code
        if params_schema is not None: obj.params_schema = json.dumps(params_schema, ensure_ascii=False)


def delete_strategy(strategy_id: int):
    with transaction() as s:
        obj = s.get(Strategy, strategy_id)
        if obj and not obj.is_builtin:
            s.delete(obj)


def list_factors(category: str = None) -> list:
    with transaction() as s:
        q = s.query(Factor).order_by(Factor.id)
        if category:
            q = q.filter(Factor.category == category)
        return [r.to_dict() for r in q.all()]


def create_custom_factor(factor_id: str, name_zh: str, category: str,
                          formula: str, params_schema: dict,
                          description: str, dsl_code: str) -> dict:
    """创建用户自定义 DSL 因子"""
    import json as _json
    with transaction() as s:
        existing = s.get(Factor, factor_id)
        if existing:
            raise ValueError(f"因子 ID 已存在: {factor_id}")
        obj = Factor(
            id=factor_id, name_zh=name_zh, category=category,
            formula=formula or "", params_schema=_json.dumps(params_schema or {}, ensure_ascii=False),
            description=description or "",
            is_custom=True, dsl_code=dsl_code,
        )
        s.add(obj)
        s.flush()
        return obj.to_dict()


def delete_custom_factor(factor_id: str):
    """删除用户自定义因子 (内置因子不允许删除)"""
    with transaction() as s:
        obj = s.get(Factor, factor_id)
        if not obj:
            return
        if not obj.is_custom:
            raise ValueError(f"内置因子不允许删除: {factor_id}")
        s.delete(obj)


def create_rule(name: str, description: str, rule_json: dict) -> int:
    with transaction() as s:
        obj = CustomRule(name=name, description=description,
                         rule_json=json.dumps(rule_json or {}, ensure_ascii=False))
        s.add(obj)
        s.flush()
        return obj.id


def list_rules() -> list:
    with transaction() as s:
        return [r.to_dict() for r in s.query(CustomRule).order_by(CustomRule.id.desc()).all()]


def delete_rule(rule_id: int):
    with transaction() as s:
        obj = s.get(CustomRule, rule_id)
        if obj:
            s.delete(obj)


def save_backtest_run(strategy_name: str, params: dict, metrics: dict) -> int:
    with transaction() as s:
        obj = BacktestRun(
            strategy_name=strategy_name,
            params=json.dumps(params or {}, ensure_ascii=False),
            metrics=json.dumps(metrics or {}, ensure_ascii=False),
        )
        s.add(obj)
        s.flush()
        return obj.id


def list_backtest_runs(limit: int = 50) -> list:
    with transaction() as s:
        return [r.to_dict() for r in
                s.query(BacktestRun).order_by(BacktestRun.id.desc()).limit(limit).all()]


def insert_trade(mode: str, symbol: str, side: str, price: float,
                 amount: float, pnl: float = 0, note: str = "") -> int:
    with transaction() as s:
        obj = Trade(mode=mode, symbol=symbol, side=side, price=price,
                    amount=amount, pnl=pnl, note=note)
        s.add(obj)
        s.flush()
        return obj.id


def list_trades(mode: str = None, limit: int = 100) -> list:
    with transaction() as s:
        q = s.query(Trade).order_by(Trade.id.desc()).limit(limit)
        if mode:
            q = q.filter(Trade.mode == mode)
        return [r.to_dict() for r in q.all()]
