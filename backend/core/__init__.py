"""core - 纯计算核心 + 共享工具

放置:
- backtest/:  回测引擎 (Backtester, compute_metrics, plot_equity)
- factor/:    33+ 因子
- strategy/:  DSL 引擎 + Python 沙箱 + 多 tf 上下文 + 9 个内置策略
- helpers.py: 通用工具 (df_dates, to_records, sanitize, fmt)
- logging.py: 日志初始化 (单例)

区别于 config/ (用户可改配置) / repositories/ (DB+网络 I/O) / services/ (业务编排):
core 强调"无副作用" — 纯计算 + 工具, 可独立单测。

DB engine 放在 repositories/models.py 里 (与 ORM 同源)。
"""
from .logging import log, setup_logger


__all__ = ["log", "setup_logger"]