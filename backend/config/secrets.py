"""敏感凭据加载: 仅从环境变量读取, 绝不落盘 / 绝不写日志

Binance 模拟盘 (Demo Mode) 的 API key/secret 通过以下环境变量提供:
    BINANCE_DEMO_API_KEY
    BINANCE_DEMO_API_SECRET

为方便本地开发, 启动时会尝试加载项目根目录的 .env 文件 (已在 .gitignore),
仅解析简单的 KEY=VALUE 行, 不引入 python-dotenv 依赖。
"""
import os
from pathlib import Path
from typing import Optional, Tuple

# 项目根目录 (与 config.py 的 CONFIG_PATH 同级)
_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _ROOT / ".env"

_KEY_ENV = "BINANCE_DEMO_API_KEY"
_SECRET_ENV = "BINANCE_DEMO_API_SECRET"

_loaded = False


def _load_dotenv_once() -> None:
    """把 .env 中尚未存在于环境的变量注入 os.environ (只执行一次)。

    真实环境变量优先于 .env, 不覆盖已有值。
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    if not _ENV_PATH.exists():
        return
    try:
        for raw in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        # .env 解析失败不应阻断启动; 不打印内容 (可能含密钥)
        pass


def get_demo_credentials() -> Tuple[Optional[str], Optional[str]]:
    """返回 (api_key, api_secret), 未配置则对应位为 None。"""
    _load_dotenv_once()
    key = os.environ.get(_KEY_ENV) or None
    secret = os.environ.get(_SECRET_ENV) or None
    return key, secret


def has_demo_credentials() -> bool:
    key, secret = get_demo_credentials()
    return bool(key and secret)


def redact(value: Optional[str]) -> str:
    """用于日志/返回前端的脱敏: 只保留首尾各 4 位。"""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"
