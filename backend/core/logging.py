"""统一日志: 文件 + 控制台双输出"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.config.paths import LOGS_DIR


_LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class SafeFormatter(logging.Formatter):
    """对 Windows GBK 终端做 unicode 转义兜底"""
    def format(self, record):
        try:
            return super().format(record)
        except UnicodeEncodeError:
            return super().format(record).encode("gbk", "replace").decode("gbk", "replace")


def setup_logger(name: str = "k7quant", level: int = logging.INFO,
                 log_file: str = "app.log") -> logging.Logger:
    """获取或创建 logger (避免重复 handler + 避免向上传到 root)"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    # 关键: 阻止 propagate, 避免日志被 root logger 再写一次 (uvicorn 给 root 装了 handler 会双写)
    logger.propagate = False
    formatter = SafeFormatter(_LOG_FORMAT, _DATE_FORMAT)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    fh = RotatingFileHandler(
        LOGS_DIR / log_file, maxBytes=10 * 1024 * 1024,
        backupCount=5, encoding="utf-8",
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


# 全局默认 logger
log = setup_logger()