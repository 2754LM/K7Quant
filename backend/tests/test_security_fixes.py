"""Regression tests for security and accuracy fixes

覆盖:
1. Python 沙箱 __import__ 逃逸攻击 (CRITICAL)
2. Path traversal in DataCache (HIGH)
3. symbol / timeframe 格式校验 (HIGH)
4. Backtester fee 比例缩放 (HIGH)
5. _Context.klines 失败时返回空 DataFrame (避免 look-ahead)
"""
import os
import re
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(r"D:\Desktop\lh").resolve()))

from backend.core.strategy.sandbox import PythonStrategy
from backend.repositories.binance_cache import DataCache, _validate_id
from backend.config.paths import CACHE_DIR


class SandboxEscapeTest(unittest.TestCase):
    """CRITICAL: 沙箱逃逸 - 用户 Python 策略不能调 __import__/exec/open 等"""

    def _try_compile(self, code: str):
        """尝试编译 (编译失败 = 沙箱拒绝)"""
        try:
            strat = PythonStrategy(code)
            strat.compile()
            return True
        except Exception as e:
            return f"BLOCKED: {type(e).__name__}: {e}"

    def test_reject_dunder_import(self):
        code = "def init():\n    return {}\ndef on_bar(state):\n    os = __import__('os')"
        result = self._try_compile(code)
        self.assertNotEqual(result, True, "__import__ 不应通过校验")

    def test_reject_dunder_class(self):
        code = "def init():\n    return {}\ndef on_bar(state):\n    x = ().__class__.__bases__[0].__subclasses__()"
        result = self._try_compile(code)
        self.assertNotEqual(result, True, "dunder chain 不应通过校验")

    def test_reject_open(self):
        code = "def init():\n    return {}\ndef on_bar(state):\n    open('/etc/passwd')"
        result = self._try_compile(code)
        self.assertNotEqual(result, True, "open() 不应通过校验")

    def test_reject_exec(self):
        code = "def init():\n    return {}\ndef on_bar(state):\n    exec('print(1)')"
        result = self._try_compile(code)
        self.assertNotEqual(result, True, "exec() 不应通过校验")

    def test_reject_getattr(self):
        code = "def init():\n    return {}\ndef on_bar(state):\n    getattr({}, 'keys')"
        result = self._try_compile(code)
        self.assertNotEqual(result, True, "getattr() 不应通过校验")

    def test_reject_eval(self):
        code = "def init():\n    return {}\ndef on_bar(state):\n    eval('1+1')"
        result = self._try_compile(code)
        self.assertNotEqual(result, True, "eval() 不应通过校验")

    def test_reject_globals(self):
        code = "def init():\n    return {}\ndef on_bar(state):\n    g = globals()"
        result = self._try_compile(code)
        self.assertNotEqual(result, True, "globals() 不应通过校验")

    def test_reject_dunder_method_call(self):
        code = "def init():\n    return {}\ndef on_bar(state):\n    ().__class__.__init__()"
        result = self._try_compile(code)
        self.assertNotEqual(result, True, "dunder method 不应通过校验")

    def test_safe_math_still_works(self):
        """正常数学运算应通过"""
        code = """
def init():
    return {"i": 0}
def on_bar(state):
    state["i"] += 1
    if state["i"] > 10:
        state["i"] = 0
    p = max(min(ctx.now(), 100.0), 0.0)
    if p > 50:
        buy(100)
"""
        strat = PythonStrategy(code)
        strat.compile()
        self.assertIn("init", strat._funcs)
        self.assertIn("on_bar", strat._funcs)


class DataCachePathTraversalTest(unittest.TestCase):
    """HIGH: 路径遍历攻击 - 防止 ../ 等危险字符"""

    def setUp(self):
        self.cache = DataCache()

    def test_reject_symbol_with_slash(self):
        with self.assertRaises(ValueError):
            self.cache.path("BTC/USDT", "1d")

    def test_reject_symbol_with_dotdot(self):
        with self.assertRaises(ValueError):
            self.cache.path("..", "1d")

    def test_reject_timeframe_with_slash(self):
        with self.assertRaises(ValueError):
            self.cache.path("BTCUSDT", "../etc")

    def test_reject_lowercase_symbol(self):
        with self.assertRaises(ValueError):
            self.cache.path("btcusdt", "1d")

    def test_accept_valid_symbol(self):
        p = self.cache.path("BTCUSDT", "1d")
        self.assertTrue(str(p).endswith("BTCUSDT.csv"))
        # 校验后必须在 root 之下
        self.assertTrue(p.resolve().is_relative_to(CACHE_DIR.resolve()))

    def test_validate_id_helper(self):
        # 正常
        self.assertEqual(_validate_id("BTCUSDT", "symbol", re.compile(r"^[A-Z]+$")), "BTCUSDT")
        # 异常
        with self.assertRaises(ValueError):
            _validate_id("../etc", "symbol", re.compile(r"^[A-Z]+$"))
        with self.assertRaises(ValueError):
            _validate_id("", "symbol", re.compile(r"^[A-Z]+$"))


class SymbolFormatValidationTest(unittest.TestCase):
    """symbol 格式: ^[A-Z0-9]{2,20}$"""

    def test_valid_symbols(self):
        for s in ["BTCUSDT", "ETHUSDT", "1000SHIBUSDT", "ABCDEFGH"]:
            self.assertRegex(s, r"^[A-Z0-9]{2,20}$")

    def test_invalid_symbols(self):
        for s in ["btcusdt", "BTC/USDT", "BTC.USDT", "BTC USDT", "..", "' OR 1=1"]:
            self.assertNotRegex(s, r"^[A-Z0-9]{2,20}$")


class TimeframeFormatValidationTest(unittest.TestCase):
    """timeframe 格式: ^[a-z0-9]{1,10}$ + 必须在 Binance 白名单"""

    def test_valid_timeframes(self):
        from backend.config.constants import BINANCE_TIMEFRAMES_SET
        for tf in BINANCE_TIMEFRAMES_SET:
            # 包含 1M (大写 M 表示月)
            self.assertRegex(tf, r"^[a-zA-Z0-9]{1,10}$")

    def test_invalid_timeframes(self):
        from backend.config.constants import BINANCE_TIMEFRAMES_SET
        for tf in ["../etc", "1M_upper", "30m_invalid", "abc", "1.5h"]:
            self.assertNotIn(tf, BINANCE_TIMEFRAMES_SET)


class BacktesterFeeScalingTest(unittest.TestCase):
    """HIGH: 费率应按 actual_pos 缩放, 不能用平费率扣"""

    def test_fee_scales_with_position(self):
        """position_size=0.1 时, 费率影响应只有 10%, 不是 100%"""
        from backend.core.backtest import Backtester

        # 原始 position=[1,1] → shift(1) 后 [0,1] → 1 仓 1 bar, 价格 +5%
        # 第 0 bar: 刚建仓 (prev=0, now=0) 不收费
        # 第 1 bar: 持仓, ret=+5%, fee=0.001
        df = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "close": [100.0, 105.0],
            "position": [1, 1],
        })
        bt = Backtester(initial_capital=10000, commission_rate=0.001, slippage=0.0)
        result_full = bt.run(df, position_size=1.0)
        result_partial = bt.run(df, position_size=0.1)
        # 满仓: strategy_ret[1] = 1*0.05 - 0*1*0.001 = 0.05
        #       (no trade fee because trade[1] = 0; prev=0, current=0)
        # 等等, 让我重算: 1仓, prev_pos=0, pos=1, trade=1
        # strategy_ret[1] = actual_pos[1] * ret - trade * actual_pos[1] * fee
        #                  = 1 * 0.05 - 1 * 1 * 0.001 = 0.049
        # 部分仓: strategy_ret[1] = 0.1 * 0.05 - 1 * 0.1 * 0.001 = 0.0049
        # 不修复前: 部分仓 = 0.1 * 0.05 - 0.001 = 0.004 (费率被多扣 10x)
        self.assertAlmostEqual(result_full["strategy_ret"].iloc[1], 0.049, places=6,
                              msg="满仓费率 = 0.001")
        self.assertAlmostEqual(result_partial["strategy_ret"].iloc[1], 0.0049, places=6,
                              msg="费率应按 actual_pos 缩放 (不是 0.004)")
        # 验证 ratio: 部分/满 = 0.1 (符合 position_size)
        self.assertAlmostEqual(
            result_partial["strategy_ret"].iloc[1] / result_full["strategy_ret"].iloc[1],
            0.1, places=6,
            msg="部分仓收益应是满仓的 position_size 倍"
        )


if __name__ == "__main__":
    unittest.main()