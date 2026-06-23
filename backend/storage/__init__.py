"""存储层: 兼容旧 import 路径, 实际逻辑在 backend.models

旧的 `from backend.storage import crud` / `from backend.storage.db import ...` 仍然能工作，
但所有实现都基于 SQLAlchemy ORM (在 backend/models.py)。
"""
# 别名以兼容旧代码: from backend.storage import crud; crud.list_symbols() 仍然可用
from backend.models import (
    # 实体
    Base, Symbol, Strategy, Factor, CustomRule, BacktestRun, Trade,
    # 引擎与事务
    get_engine, get_session, transaction,
    # 通用 repo
    Repository,
    # 业务便捷函数
    list_symbols, get_symbol, upsert_symbol, set_active_symbols,
    list_strategies, get_strategy, create_strategy, update_strategy, delete_strategy,
    list_factors,
    list_rules, create_rule, delete_rule,
    list_backtest_runs, save_backtest_run,
    list_trades, insert_trade, clear_trades,
)

# 旧 db.py 接口的别名
def get_conn():
    """兼容: 旧代码用 conn.row_factory / conn.execute, 返回 Session.connection()"""
    return get_session().connection().connection  # 底层 sqlite3 连接 (注意: 不推荐)

def init_schema(*_args, **_kwargs):
    """兼容: 新代码启动时通过 create_all 自动建表"""
    get_engine()  # 触发 create_all

def reset_db():
    """兼容: 删除所有表重新建 (调试用)"""
    from backend.models import Base
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())


# 把 crud 设为模块别名 (旧代码 crud.xxx)
class _CrudModule:
    """兼容旧的 crud.xxx 调用, 实际指向 models 的同名函数"""
    def __getattr__(self, name):
        import backend.models as m
        return getattr(m, name)
crud = _CrudModule()
