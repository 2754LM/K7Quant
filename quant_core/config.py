"""K7Quant - 币安量化回测系统 配置"""
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


SYMBOL_POOL = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT", "DOTUSDT",
    "LINKUSDT", "TRXUSDT", "LTCUSDT", "ATOMUSDT", "NEARUSDT",
    "UNIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
    "INJUSDT", "TIAUSDT", "SEIUSDT", "RNDRUSDT", "FETUSDT",
]

TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"]

DEFAULT_TIMEFRAME = "4h"
DEFAULT_CAPITAL = 10000.0
DEFAULT_COMMISSION = 0.0004   # 0.04% 双向
START_DATE = "20240101"
END_DATE = datetime.now().strftime("%Y%m%d")

# 默认策略参数
DEFAULT_PARAMS = {
    "ma_cross": {"ma_short": 7, "ma_long": 25},
    "momentum_rotation": {"top_n": 3, "hold": 12, "lookback": 24},
    "rsi": {"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70},
    "macd": {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9},
}

API_BASE = "https://api.binance.com"