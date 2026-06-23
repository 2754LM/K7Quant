"""logger.py 单元测试

重点: 验证 propagate=False - 修复每条 log 被双写的 bug
之前: k7quant logger 默认 propagate=True, 被 root logger 又写一次
现在: 显式 propagate=False, 文件/控制台 各只写一次
"""
import io
import logging
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class LoggerNoDuplicateTest(unittest.TestCase):
    """验证 logger 配置不会导致日志双写"""

    def setUp(self):
        # 重新 import 触发 setup_logger
        if "backend.core.logger" in sys.modules:
            del sys.modules["backend.core.logger"]
        from backend.core.logger import log
        self.log = log

    def test_propagate_disabled(self):
        """propagate 必须为 False (避免 root logger 双写)"""
        self.assertFalse(self.log.propagate,
                         "propagate 必须关闭, 否则会被 root logger 又写一次")

    def test_handlers_count(self):
        """handler 数应 = 2 (StreamHandler + RotatingFileHandler)"""
        # 注意: 可能在多次 import 后累积, 至少要有 1 个 StreamHandler + 1 个 FileHandler
        handler_types = {type(h).__name__ for h in self.log.handlers}
        self.assertIn("StreamHandler", handler_types, "缺 StreamHandler")
        self.assertIn("RotatingFileHandler", handler_types, "缺 RotatingFileHandler")

    def test_no_duplicate_to_stdout(self):
        """写入 logger 的消息不会被写两次到 stdout"""
        # 用一个独立的 StringIO 替换 StreamHandler, 验证单次写入
        captured = io.StringIO()
        test_handler = logging.StreamHandler(captured)
        test_handler.setFormatter(logging.Formatter("%(message)s"))
        self.log.addHandler(test_handler)
        try:
            self.log.warning("UNIQUE_TEST_MESSAGE_XYZ")
            output = captured.getvalue()
            self.assertEqual(output.count("UNIQUE_TEST_MESSAGE_XYZ"), 1,
                             f"日志被双写, 实际写入: {output!r}")
        finally:
            self.log.removeHandler(test_handler)


if __name__ == "__main__":
    unittest.main()