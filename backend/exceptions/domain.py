"""exceptions/domain.py - 业务异常基类

设计:
- DomainError 是所有业务异常的基类
- 各子异常对应一类业务错误 (策略编译 / 回测 / 数据获取 / 配置)
- 不带 HTTP 语义 (HTTP 状态码由 controllers/handlers.py 映射)
- message 直接展示给用户 (前端 toast / 日志)

用法:
    from backend.exceptions.domain import StrategyCompileError
    raise StrategyCompileError(f"DSL 解析失败: {e}")
"""
from typing import Optional


class DomainError(Exception):
    """业务异常基类 - 一切可恢复的业务错误"""
    code: str = "domain_error"

    def __init__(self, message: str, *, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self):
        if self.details:
            return f"{self.message} ({self.details})"
        return self.message


# ============ 策略相关 ============

class StrategyError(DomainError):
    """策略相关错误基类"""
    code = "strategy_error"


class StrategyCompileError(StrategyError):
    """策略编译失败 (DSL 解析错误 / Python 沙箱编译错误 / AST 白名单拒绝)"""
    code = "strategy_compile_error"


class StrategyValidationError(StrategyError):
    """策略代码验证失败 (语法错 / 缺 on_bar / 引用未知因子)"""
    code = "strategy_validation_error"


# ============ 回测相关 ============

class BacktestError(DomainError):
    """回测执行失败"""
    code = "backtest_error"


class BacktestNoDataError(BacktestError):
    """回测时数据为空"""
    code = "backtest_no_data"


# ============ 数据相关 ============

class DataError(DomainError):
    """数据获取/缓存相关错误基类"""
    code = "data_error"


class DataFetchError(DataError):
    """远端数据拉取失败 (Binance 不可达 / 404 / 超时)"""
    code = "data_fetch_error"


class DataParseError(DataError):
    """数据解析失败 (Binance 返回格式不对 / 本地缓存损坏)"""
    code = "data_parse_error"


# ============ 配置相关 ============

class ConfigError(DomainError):
    """配置错误 (YAML 格式错 / 缺关键字段 / 值越界)"""
    code = "config_error"


# ============ 交易相关 ============

class TradeError(DomainError):
    """交易执行相关错误基类"""
    code = "trade_error"


class BinanceError(TradeError):
    """Binance API 调用错误 (签名错 / 限流 / 余额不足)"""
    code = "binance_error"


class LiveTraderError(TradeError):
    """实盘 runner 错误 (未启动 / 重复启动 / 状态异常)"""
    code = "live_trader_error"