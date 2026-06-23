"""live_trader.py 单元测试

重点测试 _coerce_pct helper - 修复 '止损=0 显式禁用' 被 config 覆盖的 bug
之前: rules.get('stop_loss') or sys_config.get(...) - 0 被当 falsy 跳掉
现在: is None 检查, 0 真正禁用, 不再被 config 覆盖
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services import live_trader


class CoercePctTest(unittest.TestCase):
    """_coerce_pct 单元测试 - 验证 '止损 = 0' 显式禁用行为"""

    def test_explicit_05(self):
        """策略显式 0.05 → 返回 0.05"""
        self.assertEqual(live_trader._coerce_pct(0.05, "trading.stop_loss_pct"), 0.05)

    def test_explicit_0_disables(self):
        """策略显式 0 → 返回 0.0 (不设止损), 这是核心 bug 修复"""
        self.assertEqual(live_trader._coerce_pct(0, "trading.stop_loss_pct"), 0.0)
        self.assertEqual(live_trader._coerce_pct(0.0, "trading.take_profit_pct"), 0.0)

    def test_explicit_08(self):
        """策略显式 0.08 → 返回 0.08"""
        self.assertEqual(live_trader._coerce_pct(0.08, "trading.stop_loss_pct"), 0.08)

    def test_none_falls_back_to_config(self):
        """策略未声明 (None) → 回落到 sys_config"""
        # sys_config.get('trading.stop_loss_pct', 0) = 0.05 (from config.yaml)
        result = live_trader._coerce_pct(None, "trading.stop_loss_pct")
        # 验证回落到 config 默认值 (config.yaml 中是 0.05)
        self.assertGreater(result, 0.0, "未设置时应回落到 config 默认值")

    def test_invalid_value_raises(self):
        """非法值 (字符串) → 返回 0.0 (不抛异常)"""
        self.assertEqual(live_trader._coerce_pct("abc", "trading.stop_loss_pct"), 0.0)
        self.assertEqual(live_trader._coerce_pct(None, "trading.unknown_key"), 0.0)

    def test_float_zero_preserved(self):
        """特别测试: float 0 不被当作 falsy 跳掉 (核心修复点)"""
        # 如果用 'or' 链, 0.0 会跳到 sys_config
        # 现在用 is None, 0.0 保留
        result = live_trader._coerce_pct(0.0, "trading.stop_loss_pct")
        self.assertEqual(result, 0.0,
                         "显式 0.0 必须保留, 不能再回落 sys_config 默认值")


if __name__ == "__main__":
    unittest.main()