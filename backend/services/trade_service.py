"""交易业务: 模拟盘对接 Binance Demo Mode

simulation 模式 -> 通过签名客户端连 demo-api.binance.com (沙盒账户)。
所有真实下单同时在本地 Trade 表落一条审计记录。
live (实盘) 模式本期不支持, 直接拒绝以杜绝误连。
"""
from typing import Optional

from backend.core import config as sys_config
from backend.core import secrets
from backend.core.logger import log
from backend.data.demo_client import get_demo_client, DemoApiError
from backend.storage import crud


def _trading_cfg() -> dict:
    return sys_config.get("trading", {}) or {}


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
