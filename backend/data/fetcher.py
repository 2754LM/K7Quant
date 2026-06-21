"""Binance 行情下载 (HTTP)
支持直连 + 系统代理 (Clash 等)
"""
import os
import time
import requests
import pandas as pd
from datetime import datetime
from typing import Optional

from backend.core import config as sys_config
from backend.core.logger import log


class BinanceFetcher:
    BASE_URL = "https://api.binance.com"

    def __init__(self, base_url: str = None, timeout: int = None,
                 retries: int = None, proxies: dict = None):
        cfg = sys_config.get("data_source", {})
        self.base_url = base_url or cfg.get("api_base", self.BASE_URL)
        # 默认 5s: 网络不佳时少等, 让上层尽快 fallback
        self.timeout = timeout or int(cfg.get("timeout", 5))
        self.retries = retries or int(cfg.get("retries", 2))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "K7Quant/4.0"})
        if proxies:
            self.session.proxies.update(proxies)

    def _get_proxies(self) -> Optional[dict]:
        """从配置 + 环境变量解析代理"""
        cfg = sys_config.get("data_source.proxy", {})
        if not cfg.get("enabled"):
            # 也支持环境变量
            return None
        http = cfg.get("http") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https = cfg.get("https") or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if not http and not https:
            return None
        p = {}
        if http:
            p["http"] = http
        if https:
            p["https"] = https
        return p

    def _request(self, path: str, params: dict = None) -> dict:
        url = f"{self.base_url}{path}"
        last_err = None
        for attempt in range(self.retries):
            try:
                r = self.session.get(url, params=params or {},
                                     timeout=self.timeout)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                if attempt < self.retries - 1:
                    time.sleep(0.5 + attempt * 0.5)
        raise RuntimeError(f"Binance {path}: {last_err}")

    def klines(self, symbol: str, interval: str,
               start_ms: Optional[int] = None, end_ms: Optional[int] = None) -> list:
        """分页拉 K 线"""
        rows = []
        while True:
            params = {"symbol": symbol.upper(), "interval": interval, "limit": 1000}
            if start_ms:
                params["startTime"] = start_ms
            if end_ms:
                params["endTime"] = end_ms
            data = self._request("/api/v3/klines", params)
            if not data:
                break
            rows.extend(data)
            if len(data) < 1000 or not start_ms:
                break
            next_start = data[-1][0] + 1
            if end_ms and next_start >= end_ms:
                break
            start_ms = next_start
            time.sleep(0.2)
        return rows

    def fetch(self, symbol: str, interval: str = "1d",
              start: str = None, end: str = None) -> pd.DataFrame:
        start_ms = int(datetime.strptime(start, "%Y%m%d").timestamp() * 1000) if start else None
        end_ms = int(datetime.strptime(end, "%Y%m%d").timestamp() * 1000) + 86399999 if end else None

        raw = self.klines(symbol, interval, start_ms, end_ms)
        if not raw:
            return pd.DataFrame()

        rows = [{
            "date": pd.to_datetime(k[0], unit="ms"),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "amount": float(k[7]) if len(k) > 7 else float(k[5]) * float(k[4]),
        } for k in raw]

        df = pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        return df

    def list_usdt_symbols(self) -> list:
        """获取所有 USDT 交易对"""
        try:
            data = self._request("/api/v3/exchangeInfo")
            return [s["symbol"] for s in data.get("symbols", [])
                    if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"]
        except Exception as e:
            log.warning(f"获取交易对失败: {e}")
            return []

    def server_time(self) -> int:
        try:
            data = self._request("/api/v3/time")
            return int(data.get("serverTime", 0))
        except Exception:
            return 0

    def test_connectivity(self) -> dict:
        """测试连接, 返回诊断信息"""
        result = {
            "proxy_enabled": bool(self._get_proxies()),
            "proxy": self._get_proxies(),
            "reachable": False,
            "server_time": None,
            "error": None,
        }
        try:
            result["server_time"] = self.server_time()
            result["reachable"] = True
        except Exception as e:
            result["error"] = str(e)
        return result


_fetcher: Optional[BinanceFetcher] = None


def get_fetcher() -> BinanceFetcher:
    global _fetcher
    if _fetcher is None:
        proxies = None
        # 优先从 fetcher 内部读配置
        _fetcher = BinanceFetcher()
        # 注入代理
        p = _fetcher._get_proxies()
        if p:
            _fetcher.session.proxies.update(p)
    return _fetcher