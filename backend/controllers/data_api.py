"""数据 API"""
import re
from fastapi import APIRouter, HTTPException, Query

from backend.services import data_service
from backend.config.paths import LOGS_DIR
from backend.config.constants import BINANCE_TIMEFRAMES_SET


router = APIRouter()


# 安全: 严格白名单
_SAFE_TIMEFRAME_RE = re.compile(r"^[a-z0-9]{1,10}$")
_SAFE_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}$")


def _validate_tf(value: str) -> str:
    if not value or not _SAFE_TIMEFRAME_RE.match(value) or value not in BINANCE_TIMEFRAMES_SET:
        raise HTTPException(status_code=400, detail=f"非法 timeframe: {value!r}")
    return value


def _validate_symbol(value: str) -> str:
    if not value or not _SAFE_SYMBOL_RE.match(value):
        raise HTTPException(status_code=400, detail=f"非法 symbol: {value!r}")
    return value


@router.get("/cache")
def list_cache():
    return data_service.list_cache()


@router.delete("/cache")
def clear_cache(timeframe: str = Query(None), symbol: str = Query(None)):
    if timeframe is not None:
        _validate_tf(timeframe)
    if symbol is not None:
        _validate_symbol(symbol)
    return data_service.clear_cache(timeframe, symbol)


@router.get("/exchange-symbols")
def exchange_symbols():
    return {"symbols": data_service.get_symbols()}


@router.get("/exchange-info/{symbol}")
def exchange_info(symbol: str):
    """单个币种的交易所元信息 (filters, permissions, 状态) - 用于币种详情页"""
    _validate_symbol(symbol)
    from backend.repositories.binance_fetcher import get_fetcher
    return get_fetcher().get_symbol_info(symbol)


@router.get("/timeframes")
def list_timeframes():
    """Binance 支持的 timeframe 白名单 (前端 UI 用)
    返回顺序按 Binance 官方文档 (秒/分/时/日/周/月), 不是字母序
    """
    from backend.repositories.binance_fetcher import BINANCE_TIMEFRAMES
    return {"timeframes": list(BINANCE_TIMEFRAMES)}


@router.get("/test-connection")
def test_connection():
    # 包一层 binance, 与前端 DataPanel 读取的 res.data.binance 对齐
    return {"binance": data_service.test_connectivity()}


@router.get("/logs/tail")
def tail_logs(lines: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    """读取后端日志最近 N 行 (供前端 SystemLogPanel 轮询)"""
    import os
    log_path = LOGS_DIR / "app.log"
    if not log_path.exists():
        return {"lines": [], "offset": 0, "mtime": 0}
    try:
        mtime = log_path.stat().st_mtime
    except OSError:
        mtime = 0
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except Exception as e:
        from backend.core.logging import log
        log.warning(f"[tail_logs] 读日志失败: {e}")
        return {"lines": [], "offset": 0, "mtime": 0}
    if offset >= len(all_lines):
        return {"lines": [], "offset": len(all_lines), "mtime": mtime}
    end = len(all_lines) - offset
    start = max(0, end - lines)
    return {
        "lines": [ln.rstrip("\n") for ln in all_lines[start:end]],
        "offset": offset,
        "total": len(all_lines),
        "mtime": mtime,
    }


@router.post("/fetch")
def fetch(symbol: str, timeframe: str = "4h",
          start: str = "20240101", end: str = "20250601"):
    _validate_symbol(symbol)
    _validate_tf(timeframe)
    return data_service.fetch_one(symbol, timeframe, start, end)