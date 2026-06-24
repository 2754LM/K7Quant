"""Python 沙箱基础测试

- AST 白名单: import/async/dunder/open/exec/eval 必须拒绝
- init/on_bar 模式正常工作
- 单 bar 抛错不中断回测
- 安全 globals 暴露
"""
import ast
import unittest
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.core.strategy.sandbox import PythonStrategy, _validate_ast


class PythonSandboxSecurityTest(unittest.TestCase):
    """AST 白名单安全校验"""

    def test_reject_import(self):
        with self.assertRaises(Exception):
            _validate_ast(ast.parse("import os"))

    def test_reject_from_import(self):
        with self.assertRaises(Exception):
            _validate_ast(ast.parse("from os import path"))

    def test_reject_async(self):
        with self.assertRaises(Exception):
            _validate_ast(ast.parse("async def f(): pass"))

    def test_reject_dunder(self):
        with self.assertRaises(Exception):
            _validate_ast(ast.parse("x = obj.__class__"))

    def test_allow_simple_arithmetic(self):
        # 不应抛异常
        _validate_ast(ast.parse("x = 1 + 2; y = x * 3"))

    def test_allow_function_def(self):
        _validate_ast(ast.parse("def on_bar(state):\n    return state.get('x')"))


class PythonSandboxInitTest(unittest.TestCase):
    """init/on_bar 模式"""

    def test_compile_and_init(self):
        code = """
def init():
    return {"entry": 0.0, "qty": 0.0}

def on_bar(state):
    p = ctx.now()
    if state["entry"] == 0:
        state["entry"] = p
        buy(100)
"""
        strat = PythonStrategy(code)
        strat.compile()
        state = strat._funcs["init"]()
        self.assertEqual(state, {"entry": 0.0, "qty": 0.0})

    def test_compile_missing_on_bar(self):
        """没有 on_bar 必须报错"""
        code = "def init():\n    return {}"
        # 校验在 __init__ 时就发生
        with self.assertRaises(Exception):
            PythonStrategy(code)


class PythonSandboxRunTest(unittest.TestCase):
    """完整 run 测试"""

    @staticmethod
    def _make_df():
        # 100 根 1m K 线, 价格围绕 100 浮动
        idx = pd.date_range("2026-06-01 00:00:00", periods=100, freq="1min")
        prices = 100 + np.cumsum(np.random.RandomState(42).randn(100)) * 0.1
        return pd.DataFrame({
            "date": idx,
            "open": prices,
            "high": prices * 1.001,
            "low": prices * 0.999,
            "close": prices,
            "volume": np.ones(100) * 100,
        })

    def test_simple_strategy_runs(self):
        """简单策略: 第一根买, 然后不动"""
        code = """
def init():
    return {"bought": False}

def on_bar(state):
    if not state["bought"]:
        buy(100)
        state["bought"] = True
"""
        strat = PythonStrategy(code)
        df = self._make_df()
        result = strat.run(df, capital=10000, primary_symbol="BTCUSDT", primary_timeframe="1m")
        self.assertIn("actions", result)
        self.assertIn("final_state", result)
        self.assertTrue(any(a.get("action") == "buy" for a in result["actions"]),
                        "应当至少有一次 buy action")

    def test_single_bar_error_isolated(self):
        """on_bar 单 bar 抛错不中断回测, 仅跳过"""
        code = """
def init():
    return {"i": 0}

def on_bar(state):
    state["i"] += 1
    if state["i"] == 50:
        raise ValueError("intentional error on bar 50")
"""
        strat = PythonStrategy(code)
        df = self._make_df()
        result = strat.run(df, capital=10000, primary_symbol="BTCUSDT", primary_timeframe="1m")
        # 即使中途抛错, run 应正常返回
        self.assertEqual(result["final_state"]["i"], 100,
                         "抛错 bar 之外应继续累加")


if __name__ == "__main__":
    unittest.main()