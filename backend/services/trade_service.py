"""交易业务: 模拟盘对接 Binance Demo Mode

simulation 模式 -> 通过签名客户端连 demo-api.binance.com (沙盒账户)。
所有真实下单同时在本地 Trade 表落一条审计记录。
live (实盘) 模式本期不支持, 直接拒绝以杜绝误连。
"""
import math
from typing import Optional

from backend.core import config as sys_config
from backend.core import secrets
from backend.core.logger import log
from backend.data.demo_client import get_demo_client, DemoApiError
from backend.storage import crud

# 平仓时作为计价货币 / 不卖出的资产
_QUOTE_ASSETS = {"USDT"}


def _trading_cfg() -> dict:
    return sys_config.get("trading", {}) or {}


def _decimals_of(step_str: Optional[str]) -> int:
    s = str(step_str or "")
    if "." in s:
        return len(s.split(".")[1].rstrip("0"))
    return 0


def _floor_qty(value: float, step_str: Optional[str]) -> float:
    """按交易对步进向下取整数量 (与前端 floorToStep 一致, 避免 -1013 精度错误)。"""
    try:
        step = float(step_str or 0)
    except (TypeError, ValueError):
        step = 0
    if step <= 0:
        return float(value)
    n = math.floor((float(value) + 1e-12) / step) * step
    return float(f"{n:.{_decimals_of(step_str)}f}")


def _guard_simulation() -> Optional[dict]:
    """放行条件检查。返回 None 表示可继续, 否则返回错误响应体。"""
    cfg = _trading_cfg()
    mode = cfg.get("mode", "simulation")
    if mode == "live":
        return {"ok": False, "error": "实盘模式暂不支持, 请在设置中切换为 simulation (模拟盘)"}
    if not secrets.has_demo_credentials():
        return {"ok": False, "configured": False,
                "error": "未配置模拟盘凭据, 请设置环境变量 BINANCE_DEMO_API_KEY / BINANCE_DEMO_API_SECRET"}
    return None


# ---- 状态 ----
def get_status() -> dict:
    cfg = _trading_cfg()
    status = {
        "enabled": cfg.get("enabled", False),
        "mode": cfg.get("mode", "simulation"),
        "max_position_pct": cfg.get("max_position_pct", 0.3),
        "max_total_pct": cfg.get("max_total_pct", 0.95),
        "stop_loss_pct": cfg.get("stop_loss_pct", 0.05),
        "take_profit_pct": cfg.get("take_profit_pct", 0.15),
        "configured": secrets.has_demo_credentials(),
        "demo_connected": False,
        "balances_summary": [],
        "open_order_count": 0,
        "active_orders": 0,
        "today_pnl": 0.0,
    }
    if not secrets.has_demo_credentials():
        return status
    try:
        client = get_demo_client()
        conn = client.connectivity()
        status["demo_connected"] = conn.get("credentials_valid", False)
        if status["demo_connected"]:
            balances = client.balances()
            status["balances_summary"] = balances[:8]
            opens = client.open_orders()
            status["open_order_count"] = len(opens)
            status["active_orders"] = len(opens)
        else:
            status["error"] = conn.get("error")
    except DemoApiError as e:
        status["error"] = str(e)
    except Exception as e:
        log.warning(f"[trade] 获取状态失败: {e}")
        status["error"] = str(e)
    return status


def test_connectivity() -> dict:
    if not secrets.has_demo_credentials():
        return {"configured": False, "reachable": False, "credentials_valid": False,
                "error": "未配置 API Key/Secret"}
    try:
        return get_demo_client().connectivity()
    except Exception as e:
        return {"configured": True, "reachable": False, "credentials_valid": False,
                "error": str(e)}


# ---- 账户 ----
def get_account() -> dict:
    blocked = _guard_simulation()
    if blocked:
        return blocked
    try:
        return {"ok": True, "balances": get_demo_client().balances()}
    except DemoApiError as e:
        return {"ok": False, "error": str(e), "code": e.code}
    except Exception as e:
        log.exception("[trade] get_account 失败")
        return {"ok": False, "error": str(e)}


def get_balances() -> dict:
    return get_account()


# ---- 订单 ----
def get_open_orders(symbol: Optional[str] = None) -> dict:
    blocked = _guard_simulation()
    if blocked:
        return blocked
    try:
        return {"ok": True, "orders": get_demo_client().open_orders(symbol)}
    except DemoApiError as e:
        return {"ok": False, "error": str(e), "code": e.code}
    except Exception as e:
        log.exception("[trade] get_open_orders 失败")
        return {"ok": False, "error": str(e)}


def place_order(symbol: str, side: str, order_type: str, quantity: float,
                price: Optional[float] = None, time_in_force: str = "GTC") -> dict:
    blocked = _guard_simulation()
    if blocked:
        return blocked
    try:
        res = get_demo_client().place_order(
            symbol, side, order_type, quantity, price, time_in_force)
        # 本地审计: 成交均价优先用 成交额/成交量 (市价单 price=0), 否则退回委托价
        executed = float(res.get("executedQty") or 0)
        quote = float(res.get("cummulativeQuoteQty") or 0)
        if executed > 0 and quote > 0:
            fill_price = quote / executed
        else:
            fill_price = float(res.get("price") or 0) or (float(price) if price else 0.0)
        if executed <= 0:
            executed = float(quantity)
        try:
            crud.insert_trade(
                mode="simulation", symbol=symbol.upper(), side=side.lower(),
                price=fill_price, amount=executed, pnl=0,
                note=f"demo order #{res.get('orderId')} {res.get('status', '')}")
        except Exception as e:
            log.warning(f"[trade] 本地审计写入失败 (不影响下单): {e}")
        return {"ok": True, "order": res}
    except DemoApiError as e:
        return {"ok": False, "error": str(e), "code": e.code}
    except Exception as e:
        log.exception("[trade] place_order 失败")
        return {"ok": False, "error": str(e)}


def cancel_order(symbol: str, order_id: int) -> dict:
    blocked = _guard_simulation()
    if blocked:
        return blocked
    try:
        return {"ok": True, "order": get_demo_client().cancel_order(symbol, order_id)}
    except DemoApiError as e:
        return {"ok": False, "error": str(e), "code": e.code}
    except Exception as e:
        log.exception("[trade] cancel_order 失败")
        return {"ok": False, "error": str(e)}


def get_my_trades(symbol: str, limit: int = 50) -> dict:
    blocked = _guard_simulation()
    if blocked:
        return blocked
    try:
        return {"ok": True, "trades": get_demo_client().my_trades(symbol, limit)}
    except DemoApiError as e:
        return {"ok": False, "error": str(e), "code": e.code}
    except Exception as e:
        log.exception("[trade] get_my_trades 失败")
        return {"ok": False, "error": str(e)}


# ---- 本地审计记录 (沿用旧接口) ----
def list_trades(mode: str = None, limit: int = 100) -> list:
    return crud.list_trades(mode, limit)


def record_trade(mode: str, symbol: str, side: str, price: float,
                 amount: float, pnl: float = 0, note: str = "") -> int:
    return crud.insert_trade(mode, symbol, side, price, amount, pnl, note)


# ---- 沙盒重置 (一键平仓 + 清本地) ----
def reset_sandbox() -> dict:
    """一键沙盒重置:
    1) 撤销所有挂单; 2) 市价卖出所有非 USDT 持仓换回 USDT (dust 跳过);
    3) 清空本地审计记录 (mode=simulation)。

    返回执行报告。注意: 金额不会回到原始本金 (取决于卖出所得, 含手续费/盈亏);
    低于最小名义额的 dust 与 Binance 服务器侧成交记录无法清除。
    """
    report = {
        "ok": True, "connected": False, "cancelled": 0,
        "sold": [], "skipped_dust": [], "failed": [],
        "local_cleared": 0, "reset_at": None, "live_stopped": False,
    }
    # 若有策略实盘在跑, 先停掉, 否则它会和重置抢着下单 / 持仓状态错乱
    try:
        from backend.services.live_trader import get_live_trader
        lt = get_live_trader()
        if lt.running:
            lt.stop()
            report["live_stopped"] = True
    except Exception as e:
        log.warning(f"[trade] 重置前停止实盘运行器失败: {e}")
    blocked = _guard_simulation()
    if not blocked:
        report["connected"] = True
        client = get_demo_client()

        # 1. 撤销所有挂单 (按 symbol 分组撤)
        try:
            opens = client.open_orders()
            order_symbols = sorted({o.get("symbol") for o in opens if o.get("symbol")})
            for sym in order_symbols:
                try:
                    res = client.cancel_open_orders(sym)
                    report["cancelled"] += len(res) if isinstance(res, list) else 1
                except DemoApiError as e:
                    report["failed"].append({"step": "cancel", "symbol": sym, "error": str(e)})
        except Exception as e:
            log.warning(f"[trade] 重置撤单阶段失败: {e}")
            report["failed"].append({"step": "cancel", "error": str(e)})

        # 2. 重新拉余额 (撤单后锁定额已释放) → 市价卖出非 USDT 持仓
        try:
            balances = client.balances()
        except Exception as e:
            balances = []
            report["failed"].append({"step": "balances", "error": str(e)})

        for b in balances:
            asset = (b.get("asset") or "").upper()
            free = float(b.get("free") or 0)
            if asset in _QUOTE_ASSETS or free <= 0:
                continue
            symbol = f"{asset}USDT"
            try:
                filt = client.symbol_filters(symbol)
            except Exception as e:
                report["skipped_dust"].append({
                    "asset": asset, "free": free, "reason": f"无 USDT 交易对或规则不可用: {e}"})
                continue

            qty = _floor_qty(free, filt.get("market_step_str"))
            price = 0.0
            try:
                price = client.ticker_price(symbol)
            except Exception:
                pass
            notional = qty * price if price else 0.0
            min_qty = filt.get("min_qty") or 0
            min_notional = filt.get("min_notional") or 0

            if qty <= 0 or (min_qty and qty < min_qty) or (min_notional and price and notional < min_notional):
                report["skipped_dust"].append({
                    "asset": asset, "free": free, "est_value": round(notional, 4),
                    "reason": "低于最小可卖量 / 名义额 (dust)"})
                continue

            try:
                res = client.place_order(symbol, "SELL", "MARKET", qty)
                executed = float(res.get("executedQty") or qty)
                quote = float(res.get("cummulativeQuoteQty") or 0)
                report["sold"].append({
                    "asset": asset, "symbol": symbol, "qty": executed,
                    "quote": round(quote, 4), "order_id": res.get("orderId")})
            except DemoApiError as e:
                report["failed"].append({"step": "sell", "symbol": symbol, "error": str(e), "code": e.code})
            except Exception as e:
                report["failed"].append({"step": "sell", "symbol": symbol, "error": str(e)})

        # 重置时间基准 (服务器对齐时间, 前端据此过滤旧成交让曲线/收益归零)
        try:
            report["reset_at"] = client.server_now_ms()
        except Exception:
            report["reset_at"] = None

    # 3. 清空本地审计记录 (无论是否连接都执行)
    try:
        report["local_cleared"] = crud.clear_trades("simulation")
    except Exception as e:
        report["failed"].append({"step": "clear_local", "error": str(e)})

    report["ok"] = not any(f.get("step") in ("balances", "clear_local") for f in report["failed"])
    return report


# ---- 策略实盘运行 (委托到 LiveTrader 单例; 延迟导入避免循环依赖) ----
def live_status() -> dict:
    from backend.services.live_trader import get_live_trader
    return get_live_trader().status()


def live_start(strategy_id: int, symbol: str, timeframe: str, params: dict = None) -> dict:
    from backend.services.live_trader import get_live_trader
    return get_live_trader().start(strategy_id, symbol, timeframe, params or {})


def live_stop(flatten: bool = False) -> dict:
    from backend.services.live_trader import get_live_trader
    return get_live_trader().stop(flatten)
