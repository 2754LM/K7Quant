"""Binance 模拟盘 (Demo Mode) 签名客户端

对接 https://demo-api.binance.com —— 带 HMAC-SHA256 签名的账户/交易接口:
账户余额、下单、撤单、当前委托、成交历史。鉴权方式与正式现货 API 相同。

凭据来自环境变量 (见 backend/core/secrets.py), 绝不落盘 / 绝不写日志。
代理 / 超时 / 重试沿用与 BinanceFetcher 一致的配置。
"""
import os
import time
import hmac
import hashlib
from urllib.parse import urlencode
from typing import Optional

import requests

from backend.core import config as sys_config
from backend.core import secrets
from backend.core.logger import log


# Binance 错误码 → 中文友好提示 (只覆盖交易场景常见的)
_ERROR_HINTS = {
    -1003: "请求过于频繁, 已被限频, 请稍后再试",
    -1013: "下单不符合交易对规则 (数量/价格精度或最小名义额)",
    -1021: "本地时间与服务器偏差过大, 已尝试校准, 请重试",
    -1022: "签名校验失败, 请检查 API Secret 是否正确",
    -1100: "参数包含非法字符",
    -1102: "缺少必填参数",
    -2010: "下单被拒绝 (余额不足或不满足交易规则)",
    -2011: "撤单被拒绝 (订单不存在或已成交)",
    -2013: "订单不存在",
    -2014: "API Key 格式无效",
    -2015: "API Key 无效、权限不足或 IP 不在白名单",
}


class DemoApiError(RuntimeError):
    """携带 Binance 错误码的异常, 便于上层映射友好提示。"""

    def __init__(self, code: Optional[int], message: str):
        self.code = code
        hint = _ERROR_HINTS.get(code)
        full = f"[{code}] {message}" if code is not None else message
        if hint:
            full = f"{full} —— {hint}"
        super().__init__(full)


class BinanceDemoClient:
    BASE_URL = "https://demo-api.binance.com"

    def __init__(self, base_url: str = None, timeout: int = None, retries: int = None):
        cfg = sys_config.get("data_source", {})
        self.base_url = base_url or cfg.get("demo_api_base", self.BASE_URL)
        self.timeout = timeout or int(cfg.get("timeout", 10))
        self.retries = retries or int(cfg.get("retries", 2))
        self.recv_window = int(sys_config.get("trading.recv_window", 5000))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "K7Quant/4.0"})
        p = self._get_proxies()
        if p:
            self.session.proxies.update(p)
        self._time_offset = 0  # 本地与服务器时间差 (serverTime - localTime), ms

    # ---- 基础设施 (与 BinanceFetcher 一致的代理解析) ----
    def _get_proxies(self) -> Optional[dict]:
        cfg = sys_config.get("data_source.proxy", {})
        if not cfg.get("enabled"):
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

    def _headers(self) -> dict:
        key, _ = secrets.get_demo_credentials()
        if not key:
            raise DemoApiError(None, "未配置模拟盘 API Key (环境变量 BINANCE_DEMO_API_KEY)")
        return {"X-MBX-APIKEY": key}

    def _now_ms(self) -> int:
        return int(time.time() * 1000) + self._time_offset

    def sync_time(self) -> int:
        """与服务器对时, 记录偏移, 返回偏移量 (ms)。"""
        try:
            r = self.session.get(f"{self.base_url}/api/v3/time", timeout=self.timeout)
            r.raise_for_status()
            server = int(r.json().get("serverTime", 0))
            if server:
                self._time_offset = server - int(time.time() * 1000)
        except Exception as e:
            log.warning(f"[demo] 对时失败: {e}")
        return self._time_offset

    # ---- 请求核心 ----
    def _parse_error(self, resp: requests.Response) -> DemoApiError:
        code, msg = None, resp.text
        try:
            data = resp.json()
            code = data.get("code")
            msg = data.get("msg", resp.text)
        except Exception:
            pass
        return DemoApiError(code, msg)

    def _public_request(self, path: str, params: dict = None) -> dict:
        url = f"{self.base_url}{path}"
        r = self.session.get(url, params=params or {}, timeout=self.timeout)
        if not r.ok:
            raise self._parse_error(r)
        return r.json()

    def _signed_request(self, method: str, path: str, params: dict = None) -> dict:
        _, secret = secrets.get_demo_credentials()
        if not secret:
            raise DemoApiError(None, "未配置模拟盘 API Secret (环境变量 BINANCE_DEMO_API_SECRET)")

        url = f"{self.base_url}{path}"
        last_err: Optional[Exception] = None
        for attempt in range(self.retries):
            p = {k: v for k, v in (params or {}).items() if v is not None}
            p["timestamp"] = self._now_ms()
            p["recvWindow"] = self.recv_window
            query = urlencode(p)
            sig = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            full_url = f"{url}?{query}&signature={sig}"
            try:
                r = self.session.request(method, full_url, headers=self._headers(),
                                         timeout=self.timeout)
                if r.ok:
                    return r.json()
                err = self._parse_error(r)
                # 时间戳偏差: 校时后重试一次
                if err.code == -1021 and attempt < self.retries - 1:
                    self.sync_time()
                    last_err = err
                    continue
                raise err
            except DemoApiError:
                raise
            except Exception as e:
                last_err = e
                if attempt < self.retries - 1:
                    time.sleep(0.5 + attempt * 0.5)
        raise DemoApiError(None, f"{method} {path}: {last_err}")

    # ---- 账户 ----
    def account(self) -> dict:
        return self._signed_request("GET", "/api/v3/account")

    def balances(self, non_zero: bool = True) -> list:
        data = self.account()
        out = []
        for b in data.get("balances", []):
            free = float(b.get("free", 0))
            locked = float(b.get("locked", 0))
            if non_zero and free == 0 and locked == 0:
                continue
            out.append({
                "asset": b.get("asset"),
                "free": free,
                "locked": locked,
                "total": free + locked,
            })
        out.sort(key=lambda x: x["total"], reverse=True)
        return out

    # ---- 订单 ----
    def open_orders(self, symbol: Optional[str] = None) -> list:
        params = {"symbol": symbol.upper()} if symbol else {}
        return self._signed_request("GET", "/api/v3/openOrders", params)

    def place_order(self, symbol: str, side: str, order_type: str,
                    quantity: float, price: Optional[float] = None,
                    time_in_force: str = "GTC") -> dict:
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
        }
        if params["type"] == "LIMIT":
            params["price"] = price
            params["timeInForce"] = time_in_force
        return self._signed_request("POST", "/api/v3/order", params)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        params = {"symbol": symbol.upper(), "orderId": order_id}
        return self._signed_request("DELETE", "/api/v3/order", params)

    def my_trades(self, symbol: str, limit: int = 50) -> list:
        params = {"symbol": symbol.upper(), "limit": min(int(limit), 1000)}
        return self._signed_request("GET", "/api/v3/myTrades", params)

    def cancel_open_orders(self, symbol: str) -> list:
        """撤销某交易对的全部挂单, 返回被撤订单列表 (DELETE /openOrders)。"""
        return self._signed_request("DELETE", "/api/v3/openOrders", {"symbol": symbol.upper()})

    def ticker_price(self, symbol: str) -> float:
        """最新成交价 (公开端点, 估算名义额 / 判 dust 用)。"""
        data = self._public_request("/api/v3/ticker/price", {"symbol": symbol.upper()})
        return float(data.get("price") or 0)

    def symbol_filters(self, symbol: str) -> dict:
        """交易对下单规则 (公开 exchangeInfo): 数量步进 / 最小数量 / 最小名义额。
        市价单优先用 MARKET_LOT_SIZE 步进, 缺省 (0) 回退 LOT_SIZE。"""
        data = self._public_request("/api/v3/exchangeInfo", {"symbol": symbol.upper()})
        syms = data.get("symbols", [])
        if not syms:
            raise DemoApiError(None, f"未找到交易对 {symbol}")
        s = syms[0]
        out = {
            "symbol": s.get("symbol"), "status": s.get("status"),
            "step_str": None, "step": 0.0, "min_qty": 0.0,
            "market_step_str": None, "market_step": 0.0, "min_notional": 0.0,
        }
        for f in s.get("filters", []):
            t = f.get("filterType")
            if t == "LOT_SIZE":
                out["step_str"] = f.get("stepSize")
                out["step"] = float(f.get("stepSize") or 0)
                out["min_qty"] = float(f.get("minQty") or 0)
            elif t == "MARKET_LOT_SIZE":
                out["market_step_str"] = f.get("stepSize")
                out["market_step"] = float(f.get("stepSize") or 0)
            elif t in ("NOTIONAL", "MIN_NOTIONAL"):
                mn = f.get("minNotional") or f.get("notional")
                if mn:
                    out["min_notional"] = float(mn)
        if out["market_step"] <= 0:
            out["market_step"] = out["step"]
            out["market_step_str"] = out["step_str"]
        return out

    def server_now_ms(self) -> int:
        """与服务器对齐的当前毫秒 (作重置时间基准, 过滤旧成交用)。"""
        return self._now_ms()

    # ---- 诊断 ----
    def connectivity(self) -> dict:
        """ping + 签名探测 account, 校验凭据是否有效。"""
        key, secret = secrets.get_demo_credentials()
        result = {
            "base_url": self.base_url,
            "configured": bool(key and secret),
            "api_key_masked": secrets.redact(key),
            "reachable": False,
            "credentials_valid": False,
            "proxy_enabled": bool(self._get_proxies()),
            "error": None,
        }
        try:
            self.session.get(f"{self.base_url}/api/v3/ping", timeout=self.timeout).raise_for_status()
            result["reachable"] = True
        except Exception as e:
            result["error"] = f"无法连接 demo 端点: {e}"
            return result
        if not result["configured"]:
            result["error"] = "未配置 API Key/Secret (环境变量 BINANCE_DEMO_API_KEY / SECRET)"
            return result
        try:
            self.sync_time()
            self.account()
            result["credentials_valid"] = True
        except DemoApiError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = str(e)
        return result


_client: Optional[BinanceDemoClient] = None


def get_demo_client() -> BinanceDemoClient:
    global _client
    if _client is None:
        _client = BinanceDemoClient()
    return _client
