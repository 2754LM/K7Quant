"""exceptions - 异常处理

放置:
- domain.py:   业务异常类 (StrategyCompileError, BacktestError, BinanceError, ...)
- schemas.py:   错误响应模型 (ErrorResponse)
- handlers.py: FastAPI exception_handler (注册到 app)

设计原则:
- DomainError 基类不带 HTTP 语义, 由 controllers/handlers.py 映射状态码
- message 直接展示给用户, type 用于前端分类处理
- 所有 controller 报错都返回 ErrorResponse 结构, 前端统一处理

用法 (controller 里):
    from backend.exceptions.domain import StrategyCompileError
    raise StrategyCompileError(f"DSL 解析失败: {e}")
"""
from .domain import (
    DomainError,
    StrategyError, StrategyCompileError, StrategyValidationError,
    BacktestError, BacktestNoDataError,
    DataError, DataFetchError, DataParseError,
    ConfigError,
    TradeError, BinanceError, LiveTraderError,
)
from .schemas import ErrorResponse
from .handlers import (
    register_exception_handlers,
    domain_exception_handler,
    validation_exception_handler,
    global_exception_handler,
)


__all__ = [
    "DomainError",
    "StrategyError", "StrategyCompileError", "StrategyValidationError",
    "BacktestError", "BacktestNoDataError",
    "DataError", "DataFetchError", "DataParseError",
    "ConfigError",
    "TradeError", "BinanceError", "LiveTraderError",
    "ErrorResponse",
    "register_exception_handlers",
    "domain_exception_handler",
    "validation_exception_handler",
    "global_exception_handler",
]