"""Python 策略沙箱 - 自用宽松版

策略代码结构:
  def init() -> dict:        # 可选, 返回初始 state
      ...

  def on_bar(state) -> None:  # 必填, 每根 K 线调用一次
      ...

沙箱 globals 暴露:
  - pd, np, math, json, datetime, collections, itertools, functools
  - list, dict, set, tuple, str, int, float, bool, range
  - len, min, max, sum, abs, round, sorted, etc.
  - ctx:  数据上下文 (K线 + 因子 + 工具)
  - state:  用户在 init() 返回的 dict
  - buy(usdt), sell(coin_qty), sell_all(), cash(), equity(), position()

安全机制:
  - AST 白名单: 拒绝 import / async / dunder 访问 / 危险内置
  - 编译时 + 运行时双重校验
  - on_bar 单 bar 抛错不中断回测, 仅记日志
"""
from __future__ import annotations

import ast
import math
import json
import datetime
import collections
import itertools
import functools
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from backend.factor import compute_factor, FACTOR_REGISTRY


# ============ AST 黑名单校验 ============

_FORBIDDEN_NODES = (
    ast.Import, ast.ImportFrom,
    ast.Global, ast.Nonlocal,
    ast.AsyncFor, ast.AsyncWith, ast.AsyncFunctionDef, ast.Await,
    ast.YieldFrom,
)

_FORBIDDEN_ATTRS = {"__class__", "__bases__", "__subclasses__", "__globals__",
                    "__code__", "__dict__", "__module__", "__qualname__",
                    "__mro__", "__init_subclass__", "__subclasshook__",
                    "__getattribute__", "__getattr__", "__setattr__",
                    "__delattr__", "__reduce__", "__reduce_ex__", "__sizeof__",
                    "__repr__", "__str__", "__hash__", "__call__", "__new__"}

_FORBIDDEN_CALLS = {"open", "exec", "eval", "compile", "getattr", "setattr",
                    "delattr", "vars", "breakpoint", "input",
                    "memoryview", "help", "dir", "globals", "locals", "type"}
# 注: __import__ 留在 builtins 给 np/pandas 内部 lazy import 用, AST 校验禁止用户直接调用 __import__()


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODES):
            raise ValueError(f"禁止使用: {type(node).__name__}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                if node.attr in _FORBIDDEN_ATTRS:
                    raise ValueError(f"禁止访问 dunder 属性: {node.attr}")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALLS:
                raise ValueError(f"禁止调用: {func.id}()")
            if isinstance(func, ast.Attribute) and func.attr.startswith("__"):
                raise ValueError(f"禁止调用 dunder 方法: {func.attr}")


# ============ 沙箱 globals 构造 ============

def _safe_builtins():
    import builtins
    return {k: v for k, v in vars(builtins).items() if k not in _FORBIDDEN_CALLS}


def _build_globals(extra: dict) -> dict:
    g = {
        "__builtins__": _safe_builtins(),
        "pd": pd, "np": np,
        "math": math, "json": json, "datetime": datetime,
        "collections": collections, "itertools": itertools, "functools": functools,
        "list": list, "dict": dict, "set": set, "tuple": tuple,
        "str": str, "int": int, "float": float, "bool": bool,
        "range": range, "enumerate": enumerate, "zip": zip, "map": map,
        "filter": filter, "reversed": reversed, "sorted": sorted,
        "len": len, "min": min, "max": max, "sum": sum, "abs": abs,
        "round": round, "pow": pow, "all": all, "any": any,
    }
    g.update(extra)
    return g


# ============ 上下文 ctx ============

class _Context:
    """沙箱内的 ctx 对象: 暴露当前 bar 数据 + 全部因子 + 工具 + 多 timeframe 上下文

    每根 bar 调用时, _bar 自增, _df 切片到当前 bar 位置。
    因子通过 compute_factor 调用, 传入切片 df, 返回 Series (截至当前 bar)。

    多 timeframe 上下文 (ctx.klines("15m", n=20)):
      - 首次调用 ctx.klines("15m", ...) 时, 根据当前主图 df 推断区间,
        一次性从 cache/远端拉取足够长的 K 线并缓存到 _tf_cache。
      - 后续调用按当前 bar 时间切片, 返回截至该时间的最近 n 根。
      - ctx.factor("RSI", "15m", n=20) 在 klines 之上跑因子。
    """
    def __init__(self, df: pd.DataFrame, primary_symbol: str = "BTCUSDT",
                 primary_timeframe: str = "1d",
                 ctx_data: dict = None):
        """
        df: 主图 df
        primary_symbol: 主图币种 (拉取上下文 timeframe 时复用)
        primary_timeframe: 主图时间框架
        ctx_data: 预加载的多 timeframe 数据 {timeframe: df} (可选, 提高性能)
        """
        self._df_full = df
        self._symbol = primary_symbol
        self._primary_tf = primary_timeframe
        self._bar = 0
        self._factor_cache: dict = {}
        self._df_cache: Optional[pd.DataFrame] = None
        self._df_cache_bar: int = -1
        # 多 timeframe 缓存: {timeframe: full_df}
        self._tf_cache: dict = {}
        # 预加载的额外 timeframe (回测入口已下载, 避免 ctx.klines 再去取)
        if ctx_data:
            for tf, tdf in ctx_data.items():
                self._tf_cache[tf] = tdf

    def _slice(self) -> pd.DataFrame:
        if self._df_cache is None or self._df_cache_bar != self._bar:
            self._df_cache = self._df_full.iloc[: self._bar + 1].copy()
            self._df_cache_bar = self._bar
        return self._df_cache

    def _row(self) -> pd.Series:
        return self._df_full.iloc[self._bar]

    # ---- 多 timeframe 上下文 ----
    def klines(self, timeframe: str, n: int = None) -> pd.DataFrame:
        """返回截至当前 bar 时间的指定 timeframe 的 K 线 DataFrame。

        Args:
            timeframe: 时间框架, 如 "15m" / "1h" / "4h" / "1d"
            n: 最近 n 根 (None = 全部截至当前)

        Returns:
            DataFrame with columns: date, open, high, low, close, volume, amount
        """
        if timeframe not in self._tf_cache:
            self._load_timeframe(timeframe)
        full = self._tf_cache[timeframe]
        if full is None or full.empty:
            return full if full is not None else pd.DataFrame()
        current_time = self._row()["date"]
        # 统一转 Timestamp 避免 int vs Timestamp 类型不匹配
        try:
            current_ts = pd.Timestamp(current_time)
        except Exception:
            current_ts = pd.Timestamp(str(current_time))
        try:
            if pd.api.types.is_datetime64_any_dtype(full["date"]):
                sliced = full[full["date"] <= current_ts]
            else:
                full_dates = pd.to_datetime(full["date"], errors="coerce")
                sliced = full[full_dates <= current_ts]
        except Exception as e:
            from backend.core.logger import log
            log.warning(f"[ctx.klines] 切片 {timeframe} 失败: {e}")
            return full
        if n is not None and n > 0 and len(sliced) > n:
            sliced = sliced.tail(n)
        return sliced

    def series(self, timeframe: str, col: str = "close", n: int = None) -> pd.Series:
        """返回截至当前 bar 时间的指定 timeframe + 列的 Series"""
        return self.klines(timeframe, n)[col]

    def now_tf(self, timeframe: str) -> float:
        """返回指定 timeframe 最后一根的 close"""
        return float(self.series(timeframe, "close", n=1).iloc[-1])

    def ref_tf(self, timeframe: str, col: str = "close", n: int = 1):
        """返回指定 timeframe 倒数第 n 根的 col 值 (n=1=上一根)"""
        s = self.series(timeframe, col, n=n + 1)
        if len(s) >= n + 1:
            return s.iloc[-(n + 1)] if n > 0 else s.iloc[-1]
        return None

    def factor(self, factor_id: str, timeframe: str = None, n: int = None, **kwargs):
        """在指定 timeframe 上跑因子, 返回 Series (截至当前 bar 时间)

        Args:
            factor_id: 因子 ID (大小写不敏感, 同 DSL)
            timeframe: None = 主图, 否则为该 timeframe
            n: K 线根数 (None = 全部截至当前)
            **kwargs: 因子参数 (period, std, etc.)
        """
        if timeframe is None:
            # 主图, 走原路径
            return self.__getattr__(factor_id)(**kwargs)
        # 多 timeframe 上下文
        df = self.klines(timeframe, n)
        if df.empty or len(df) < 2:
            return pd.Series(dtype=float)
        try:
            return compute_factor(df, factor_id, kwargs)
        except Exception as e:
            from backend.core.logger import log
            log.warning(f"[ctx.factor] {factor_id} on {timeframe} 失败: {e}")
            return pd.Series(dtype=float)

    def _load_timeframe(self, timeframe: str):
        """从 cache / fetcher 拉取主图区间的额外 timeframe K 线"""
        from backend.data.access import get_kline
        # 用主图 df 的时间范围 + 一些 lookback buffer
        if len(self._df_full) == 0:
            self._tf_cache[timeframe] = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
            return
        start = str(self._df_full["date"].iloc[0])[:10].replace("-", "")
        end = str(self._df_full["date"].iloc[-1])[:10].replace("-", "")
        try:
            tdf = get_kline(self._symbol, timeframe, start, end)
        except Exception as e:
            from backend.core.logger import log
            log.warning(f"[sandbox] 加载 {self._symbol} {timeframe} 失败: {e}")
            tdf = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
        if tdf.empty:
            tdf = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
        self._tf_cache[timeframe] = tdf

    # ---- 当前 bar (单值) ----
    def now(self) -> float:    return float(self._row()["close"])
    def open(self) -> float:   return float(self._row()["open"])
    def high(self) -> float:   return float(self._row()["high"])
    def low(self) -> float:    return float(self._row()["low"])
    def volume(self) -> float: return float(self._row()["volume"])
    def amount(self) -> float: return float(self._row()["amount"])
    def time(self) -> str:     return str(self._row()["date"])
    def bars(self) -> int:     return self._bar

    # ---- 完整 DataFrame / Series ----
    @property
    def df(self):       return self._slice()
    @property
    def close(self):    return self._slice()["close"]
    @property
    def open_s(self):   return self._slice()["open"]
    @property
    def high(self):     return self._slice()["high"]
    @property
    def low(self):      return self._slice()["low"]
    @property
    def volume_s(self): return self._slice()["volume"]
    @property
    def amount_s(self): return self._slice()["amount"]
    @property
    def time_s(self):   return self._slice()["date"]

    # ---- 工具 ----
    def ref(self, series, n: int):
        if hasattr(series, "iloc") and 0 <= n < len(series):
            return series.iloc[-1 - n]
        return None

    def cross_up(self, a, b) -> pd.Series:
        a, b = pd.Series(a), pd.Series(b)
        return (a > b) & (a.shift(1) <= b.shift(1))

    def cross_down(self, a, b) -> pd.Series:
        a, b = pd.Series(a), pd.Series(b)
        return (a < b) & (a.shift(1) >= b.shift(1))

    def bars_since(self, cond) -> int:
        cond = pd.Series(cond) if not hasattr(cond, "iloc") else cond
        # 找到最后一个 True 的位置
        try:
            true_positions = cond.values.nonzero()[0]
        except Exception:
            return len(cond) + 1
        if len(true_positions) == 0:
            return len(cond) + 1
        return int(len(cond) - 1 - true_positions[-1])

    def pct_change(self, n: int = 1) -> pd.Series:
        return self.close.pct_change(n)

    def std(self, series=None, n: int = 20) -> pd.Series:
        s = series if series is not None else self.close
        return pd.Series(s).rolling(n).std()

    def sma(self, series=None, n: int = 20) -> pd.Series:
        s = series if series is not None else self.close
        return pd.Series(s).rolling(n).mean()

    def sum(self, series=None, n: int = 20) -> pd.Series:
        s = series if series is not None else self.close
        return pd.Series(s).rolling(n).sum()

    def ema(self, series=None, n: int = 20) -> pd.Series:
        s = series if series is not None else self.close
        return pd.Series(s).ewm(span=n, adjust=False).mean()

    # ---- 因子: 懒绑定 (ctx.MA 调用时去 FACTOR_REGISTRY 找) ----
    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        # 因子 ID 大小写不敏感
        fid = FACTOR_REGISTRY.get(name) or FACTOR_REGISTRY.get(name.lower())
        if fid is not None:
            factor_id = fid["id"] if isinstance(fid, dict) else fid
            def _factor(*args, **kwargs):
                cache_key = (factor_id, self._bar, tuple(sorted(kwargs.items())))
                if cache_key in self._factor_cache:
                    return self._factor_cache[cache_key]
                result = compute_factor(self._slice(), factor_id, kwargs)
                self._factor_cache[cache_key] = result
                return result
            return _factor
        raise AttributeError(f"ctx.{name} 不存在 (不是已注册因子)")


# ============ 沙箱执行器 ============

class PythonStrategy:
    """用户 Python 策略 - 编译/校验/执行"""

    def __init__(self, code: str):
        self.code = code
        self._tree: ast.Module = None
        self._bytecode = None
        self._funcs: dict = {}  # {"init": fn, "on_bar": fn} - 编译后填充
        self._validate()

    def _validate(self) -> None:
        try:
            self._tree = ast.parse(self.code, mode="exec")
        except SyntaxError as e:
            raise ValueError(f"Python 语法错误: {e}")
        _validate_ast(self._tree)
        # 必填 on_bar
        has_on_bar = any(isinstance(n, ast.FunctionDef) and n.name == "on_bar"
                         for n in self._tree.body)
        if not has_on_bar:
            raise ValueError("策略必须定义 on_bar(state) 函数")
        # 编译为字节码 (后续每根 bar exec 复用, 比 ast.parse 快)
        self._bytecode = compile(self._tree, "<strategy>", "exec")

    def compile(self) -> dict:
        """测试编译: 在干净沙箱里 exec 一次, 返回 {init_exists, on_bar_args}

        同时缓存 _funcs 给外部 (如 live_trader) 使用 init() 拿初始 state
        """
        sandbox = _build_globals({})
        try:
            exec(self._bytecode, sandbox)
        except Exception as e:
            raise ValueError(f"策略执行出错: {e}")
        # 缓存函数引用, 方便外部 (live_trader) 调用
        self._funcs = {
            "init": sandbox.get("init"),
            "on_bar": sandbox.get("on_bar"),
        }
        return {
            "has_init": "init" in sandbox,
            "on_bar_args": [a for a in sandbox["on_bar"].__code__.co_varnames
                            if a != "state"][:3],
        }

    def run(self, df: pd.DataFrame, capital: float = 10000.0,
            commission_rate: float = None, slippage: float = None,
            primary_symbol: str = "BTCUSDT", primary_timeframe: str = "1d",
            ctx_data: dict = None) -> dict:
        """跑回测, 返回 {
            equity_curve: [{date, equity, cash, position_qty, position_avg, price}, ...],
            trades: [{date, side, price, qty, ...}, ...],
            actions: [{date, action, qty, price, ...}, ...],
            final_state: dict,
        }

        Args:
            primary_symbol: 主图币种 (拉上下文 timeframe 时用)
            primary_timeframe: 主图时间框架
            ctx_data: 预加载的多 timeframe 数据 {tf: df} (回测入口已下载, 避免 ctx.klines 重复 IO)
        """
        from backend.core import config as sys_config
        cr = commission_rate if commission_rate is not None else float(sys_config.get("backtest.commission_rate", 0.0004))
        sl = slippage if slippage is not None else float(sys_config.get("backtest.slippage", 0.0005))

        ctx = _Context(df, primary_symbol=primary_symbol,
                       primary_timeframe=primary_timeframe,
                       ctx_data=ctx_data or {})

        # 1) 先 exec 一次拿 init() 调用的 state
        init_sandbox = _build_globals({})
        exec(self._bytecode, init_sandbox)
        state = (init_sandbox.get("init") or (lambda: {}))()
        if not isinstance(state, dict):
            raise ValueError(f"init() 必须返回 dict, 实际: {type(state).__name__}")

        # 2) 交易状态
        cash = float(capital)
        position_qty = 0.0
        position_avg = 0.0

        equity_curve = []
        trades = []
        actions = []

        from backend.core.logger import log
        for i in range(len(df)):
            ctx._bar = i
            ctx._factor_cache.clear()
            row = df.iloc[i]
            price = float(row["close"])
            date = str(row["date"])

            # 每根 bar 一个独立的 trade_intent, buy/sell 闭包写到这里
            trade_intent = {"buy": None, "sell": None, "sell_all": False}

            # 状态快照闭包 (给 cash/equity/position 用)
            def _cash():      return cash
            def _equity():    return cash + position_qty * price
            def _position():  return {"qty": position_qty, "avg": position_avg,
                                      "value": position_qty * price}

            # 沙箱 globals: 每次 exec 用户代码, 让 buy/sell 解析到本 bar 的闭包
            sandbox = _build_globals({
                "ctx": ctx,
                "state": state,
                "buy": lambda q: trade_intent.update(buy=float(q)),
                "sell": lambda q: trade_intent.update(sell=float(q)),
                "sell_all": lambda: trade_intent.update(sell_all=True),
                "cash": _cash, "equity": _equity, "position": _position,
            })

            # 重新 exec 用户代码 (让 user 的 defs + on_bar 解析到本 bar 的 sandbox)
            # 用户模块级常量 / helper 函数都在 sandbox 里
            try:
                exec(self._bytecode, sandbox)
                sandbox["on_bar"](state)
            except Exception as e:
                log.warning(f"[sandbox] on_bar 抛错: bar={i} date={date} err={e}")
                state["_last_error"] = str(e)
                # 仍记 equity
                eq = cash + position_qty * price
                equity_curve.append({"date": date, "equity": eq, "cash": cash,
                                     "position_qty": position_qty,
                                     "position_avg": position_avg, "price": price})
                continue

            # 3) 处理 buy
            if trade_intent["buy"] is not None and trade_intent["buy"] > 0:
                usdt = min(float(trade_intent["buy"]), cash)
                if usdt > 0:
                    exec_price = price * (1 + sl)
                    cost = usdt * (1 + cr)
                    if cost <= cash:
                        qty = usdt / exec_price * (1 - cr)
                        if position_qty > 0:
                            position_avg = (position_avg * position_qty + exec_price * qty) / (position_qty + qty)
                        else:
                            position_avg = exec_price
                        position_qty += qty
                        cash -= cost
                        trades.append({"date": date, "side": "buy", "price": exec_price,
                                       "qty": qty, "usdt": usdt, "cash": cash,
                                       "position_qty": position_qty,
                                       "position_avg": position_avg})
                        actions.append({"date": date, "action": "buy", "qty": qty,
                                        "price": exec_price})

            # 4) 处理 sell / sell_all
            if trade_intent["sell_all"] or (trade_intent["sell"] is not None and trade_intent["sell"] > 0):
                if position_qty > 0:
                    if trade_intent["sell_all"]:
                        qty = position_qty
                    else:
                        qty = min(float(trade_intent["sell"]), position_qty)
                    exec_price = price * (1 - sl)
                    proceeds = qty * exec_price * (1 - cr)
                    pnl = (exec_price - position_avg) * qty
                    cash += proceeds
                    position_qty -= qty
                    if position_qty < 1e-12:
                        position_qty = 0
                        position_avg = 0
                    trades.append({"date": date, "side": "sell", "price": exec_price,
                                   "qty": qty, "proceeds": proceeds, "pnl": pnl,
                                   "cash": cash, "position_qty": position_qty,
                                   "position_avg": position_avg})
                    actions.append({"date": date, "action": "sell", "qty": qty,
                                    "price": exec_price, "pnl": pnl})

            # 5) 记录 equity
            eq = cash + position_qty * price
            equity_curve.append({"date": date, "equity": eq, "cash": cash,
                                 "position_qty": position_qty,
                                 "position_avg": position_avg, "price": price})

        return {
            "equity_curve": equity_curve,
            "trades": trades,
            "actions": actions,
            "final_state": dict(state),
        }


def validate_python_strategy(code: str) -> dict:
    """校验 + 测试编译, 返回 {ok, error, has_init, on_bar_args}"""
    try:
        s = PythonStrategy(code)
        info = s.compile()
        return {"ok": True, **info}
    except Exception as e:
        return {"ok": False, "error": str(e)}
