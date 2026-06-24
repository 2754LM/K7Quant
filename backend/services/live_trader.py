"""策略实盘运行器: 单标的, 按 K 线收盘评估信号 + 高频监控止损止盈, 在 demo 账户下真实市价单。

约束:
- 只支持 simulation 模式 (Binance Demo Mode); live 模式被 _guard_simulation 拒绝。
- 同一进程同一时间只跑一个策略 (单例 + 后台线程)。
- 现货账户只能做多: 负信号 (做空) 一律压成空仓。
- 行情走公开 API (get_kline, use_cache=False 强制最新), 成交在 demo 账户, 价格可能有偏差。
- 后端重启不自动续跑 (线程随进程结束)。
- 支持 DSL 和 Python 两种 code_type (Python 走 PythonStrategy 沙箱 + on_bar 状态机)
- 支持多 timeframe 上下文 (context_timeframes, 在 evaluate 时拉取 ctx_data)
"""
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from backend.config import config as sys_config
from backend.core.logging import log
from backend.repositories.binance_data import get_kline
from backend.repositories.demo_client import get_demo_client, DemoApiError
from backend.core.strategy import StrategyEngine
from backend.core.strategy.sandbox import PythonStrategy
from backend.core.strategy.context import build_ctx_series
from backend.repositories.crud import crud
from backend.services.trade_service import _floor_qty, _guard_simulation


# 周期 -> 秒
_TF_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800,
}
_SLTP_TICK_SECONDS = 20      # 止损止盈监控频率
_LOOKBACK_BARS = 320         # 评估信号时回看的 K 线根数 (够 MA99 等长周期因子)
_MAX_LOG = 200


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _coerce_pct(rule_value, config_key: str) -> float:
    """止损/止盈取值: 优先用策略里显式声明的值 (即使是 0 = 不设止损),
    策略未声明时回落到 sys_config, 都没有才返回 0。
    用 `is None` 而不是 `or` 避免 0 被当 falsy 跳掉。
    """
    if rule_value is not None:
        try:
            return float(rule_value)
        except (TypeError, ValueError):
            return 0.0
    cfg = sys_config.get(config_key, 0)
    try:
        return float(cfg) if cfg is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _base_asset(symbol: str) -> str:
    s = symbol.upper()
    return s[:-4] if s.endswith("USDT") else s


class LiveTrader:
    def __init__(self):
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._signal_fn = None         # DSL signal_fn(df) -> Series
        self._py_runner = None         # PythonStrategy instance (Python mode)
        self._py_state = None          # Python mode 的 state (跨 tick 保留)
        self._py_capital = 10000.0     # Python mode 的虚拟本金 (用于回算 pos_avg)
        self._code = ""
        self._code_type = "dsl"
        self._ctx_tfs: list = []
        self._ctx_lookback: int = 20
        self._ctx_cache: dict = {}     # 缓存 ctx_data
        self._reset_state()

    # ---- 状态 ----
    def _reset_state(self):
        self.running = False
        self.strategy_id = None
        self.strategy_name = ""
        self.symbol = ""
        self.timeframe = ""
        self.params = {}
        self.position = "flat"        # flat / long
        self.entry_price = 0.0
        self.qty = 0.0
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.position_size = 1.0
        self.last_signal = None
        self.last_eval_bar = None     # 上次评估的已收盘 bar 开盘 ms (去重)
        self.last_action = ""
        self.last_price = 0.0
        self.started_at = None
        self.updated_at = None
        self.error = ""
        self.logs = []
        self.code_type = "dsl"
        self.context_timeframes = []

    def status(self) -> dict:
        return {
            "running": self.running,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "code_type": self.code_type,
            "context_timeframes": self.context_timeframes,
            "position": self.position,
            "entry_price": round(self.entry_price, 6),
            "qty": self.qty,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_size": self.position_size,
            "last_signal": self.last_signal,
            "last_action": self.last_action,
            "last_price": round(self.last_price, 6),
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "logs": self.logs[-50:],
        }

    def _log(self, msg: str):
        self.logs.append({"time": _now_iso(), "msg": msg})
        if len(self.logs) > _MAX_LOG:
            self.logs = self.logs[-_MAX_LOG:]
        log.info(f"[live] {msg}")

    def _set_error(self, msg: str):
        self.error = msg
        self._log(f"⚠️ {msg}")

    # ---- 控制 ----
    def start(self, strategy_id: int, symbol: str, timeframe: str = "1m", params: dict = None) -> dict:
        blocked = _guard_simulation()
        if blocked:
            return blocked
        with self._lock:
            if self.running or (self._thread and self._thread.is_alive()):
                return {"ok": False, "error": "已有策略在运行, 请先停止"}
            if timeframe not in _TF_SECONDS:
                return {"ok": False, "error": f"不支持的周期: {timeframe}"}
            strat = crud.get_strategy(strategy_id)
            if not strat:
                return {"ok": False, "error": f"策略 ID {strategy_id} 不存在"}
            self._code = strat["code"]
            self._code_type = strat.get("code_type", "dsl") or "dsl"
            self._ctx_tfs = strat.get("context_timeframes") or []
            self._ctx_lookback = int(strat.get("context_lookback") or 20)
            self._ctx_cache = {}

            try:
                if self._code_type == "python":
                    self._py_runner = PythonStrategy(self._code)
                    # 先 compile 才能拿到 funcs
                    self._py_runner.compile()
                    # 调 init() 拿初始 state
                    init_fn = self._py_runner._funcs.get("init")
                    self._py_state = init_fn() if init_fn else {}
                    if not isinstance(self._py_state, dict):
                        self._py_state = {}
                    self._py_capital = float(
                        (params or {}).get("capital") or sys_config.get("backtest.initial_capital", 10000)
                    )
                    # Python 模式的止损止盈/仓位从 config 取 (Python 策略一般没有
                    # DSL 那样的止损= 语法, 所以这里直接用 config; 0 表示不设)。
                    rules = {
                        "stop_loss": float(sys_config.get("trading.stop_loss_pct", 0) or 0),
                        "take_profit": float(sys_config.get("trading.take_profit_pct", 0) or 0),
                        "position_size": float(sys_config.get("trading.max_position_pct", 1.0) or 1.0),
                    }
                    # 但用户可能通过 params 传入 stop_loss / take_profit 显式覆盖
                    for k in ("stop_loss", "take_profit", "position_size"):
                        if k in (params or {}):
                            rules[k] = float(params[k])
                else:
                    self._py_runner = None
                    self._py_state = None
                    # DSL: 拉 ctx_data 并编译
                    ctx_info = self._load_ctx_data()
                    self._signal_fn, rules = StrategyEngine.compile(
                        self._code, params or {},
                        ctx_series=ctx_info["ctx_series"],
                        ctx_extra_cols=ctx_info["ctx_extra_cols"],
                    )
                    if self._ctx_tfs:
                        rules["context_timeframes"] = self._ctx_tfs
                        rules["context_lookback"] = self._ctx_lookback
            except Exception as e:
                import traceback
                log.error(f"[live] 策略编译失败:\n{traceback.format_exc()}")
                return {"ok": False, "error": f"策略编译失败: {e}"}

            self._reset_state()
            self.strategy_id = strategy_id
            self.strategy_name = strat["name"]
            self.symbol = symbol.upper()
            self.timeframe = timeframe
            self.params = params or {}
            self.stop_loss = _coerce_pct(rules.get("stop_loss"), "trading.stop_loss_pct")
            self.take_profit = _coerce_pct(rules.get("take_profit"), "trading.take_profit_pct")
            self.position_size = float(rules.get("position_size") or 1.0)
            self.code_type = self._code_type
            self.context_timeframes = list(self._ctx_tfs)
            self.running = True
            self.started_at = _now_iso()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="live-trader")
            self._thread.start()
            return {"ok": True, "status": self.status()}

    def stop(self, flatten: bool = False) -> dict:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=8)
        if flatten and self.position == "long":
            try:
                self._sell_all(self._current_price(), reason="停止平仓")
            except Exception as e:
                self._set_error(f"停止平仓失败: {e}")
        self.running = False
        self.updated_at = _now_iso()
        return {"ok": True, "status": self.status()}

    def _load_ctx_data(self) -> dict:
        """拉主图 + 上下文 K 线, 构建 ctx_series / ctx_extra_cols / ctx_data"""
        if not self._ctx_tfs:
            return {"ctx_series": {}, "ctx_extra_cols": set(), "ctx_data": {}}
        # 拉主图
        tf_sec = _TF_SECONDS.get(self.timeframe, 3600)
        lookback_days = max(2, int((_LOOKBACK_BARS * tf_sec) / 86400) + 1)
        start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")
        end = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
        try:
            main_df = get_kline(self.symbol, self.timeframe, start, end, use_cache=False)
        except Exception as e:
            log.warning(f"[live] 拉主图 {self.symbol} {self.timeframe} 失败: {e}")
            main_df = None
        if main_df is None or main_df.empty:
            return {"ctx_series": {}, "ctx_extra_cols": set(), "ctx_data": {}}
        try:
            return build_ctx_series(main_df, self.symbol, self.timeframe,
                                    self._ctx_tfs, self._ctx_lookback)
        except Exception as e:
            log.warning(f"[live] build_ctx_series 失败: {e}")
            return {"ctx_series": {}, "ctx_extra_cols": set(), "ctx_data": {}}

    # ---- 主循环 ----
    def _run(self):
        tf_sec = _TF_SECONDS.get(self.timeframe, 3600)
        try:
            self._sync_position_from_account()
            self._log(f"启动: {self.strategy_name} · {self.symbol} · {self.timeframe} · "
                      f"type={self._code_type} · ctx={self._ctx_tfs} · "
                      f"仓位={self.position} · 止损={self.stop_loss} 止盈={self.take_profit}")
        except Exception as e:
            self._set_error(f"启动同步持仓失败: {e}")
            import traceback; log.exception(f"[live] 启动异常: {e}\n{traceback.format_exc()}")

        while not self._stop.is_set():
            try:
                price = self._current_price()
                if price > 0:
                    self.last_price = price
                # 1. 止损/止盈 (持仓时每个 tick 检查)
                self._check_stop_take(price)
                # 2. 信号评估 (仅在新 bar 收盘后)
                bar_id = self._closed_bar_id(tf_sec)
                if not self._stop.is_set() and bar_id != self.last_eval_bar:
                    self._evaluate_signal(price)
                    self.last_eval_bar = bar_id
                self.error = ""
                self.updated_at = _now_iso()
            except DemoApiError as e:
                self._set_error(str(e))
            except Exception as e:
                self._set_error(str(e))
                import traceback
                log.exception(f"[live] 循环异常: {e}\n{traceback.format_exc()}")
            self._stop.wait(_SLTP_TICK_SECONDS)

        self.running = False
        self.updated_at = _now_iso()
        self._log("已停止")

    def _closed_bar_id(self, tf_sec: int) -> int:
        """最近已收盘 bar 的开盘时间 (秒级 epoch), 作为去重 id。"""
        now = int(time.time())
        cur_open = (now // tf_sec) * tf_sec     # 当前正在形成的 bar 开盘
        return cur_open - tf_sec                # 上一根 (最近收盘) 的开盘

    # ---- 行情 / 持仓 ----
    def _current_price(self) -> float:
        try:
            return float(get_demo_client().ticker_price(self.symbol))
        except Exception:
            return self.last_price or 0.0

    def _free(self, asset: str) -> float:
        for b in get_demo_client().balances():
            if (b.get("asset") or "").upper() == asset.upper():
                return float(b.get("free") or 0)
        return 0.0

    def _sync_position_from_account(self):
        """启动时按账户实际余额判定当前是否持仓 (避免与已有持仓打架)。"""
        base = _base_asset(self.symbol)
        free = self._free(base)
        price = self._current_price()
        if free > 0 and price > 0 and free * price >= 5:
            self.position = "long"
            self.qty = free
            if self.entry_price <= 0:
                self.entry_price = price     # 历史成本未知, 以当前价作基准
            self._log(f"检测到已有持仓 {free} {base}, 以现价 {price:.4f} 作止损止盈基准")
        else:
            self.position = "flat"

    # ---- 风控 ----
    def _check_stop_take(self, price: float):
        if self.position != "long" or price <= 0 or self.entry_price <= 0:
            return
        chg = (price - self.entry_price) / self.entry_price
        if self.stop_loss > 0 and chg <= -self.stop_loss:
            self._sell_all(price, reason=f"止损 {chg * 100:.2f}%")
        elif self.take_profit > 0 and chg >= self.take_profit:
            self._sell_all(price, reason=f"止盈 +{chg * 100:.2f}%")

    # ---- 信号 ----
    def _evaluate_signal(self, price: float):
        tf_sec = _TF_SECONDS.get(self.timeframe, 3600)
        now_dt = datetime.now()
        lookback_days = max(2, int((_LOOKBACK_BARS * tf_sec) / 86400) + 1)
        start = (now_dt - timedelta(days=lookback_days)).strftime("%Y%m%d")
        # end 必须用「明天」: get_kline 的 _filter 是 date <= end(当天0点UTC),
        # 用今天会把今天一整天的日内 K 线全过滤掉, 信号就冻结在 0 点那根 -> 永不翻转。
        end = (now_dt + timedelta(days=1)).strftime("%Y%m%d")
        try:
            df = get_kline(self.symbol, self.timeframe, start, end, use_cache=False)
        except Exception as e:
            self._set_error(f"拉 K 线失败: {e}")
            return
        if df is None or df.empty or len(df) < 5:
            self._log("K线不足, 跳过本次评估")
            return
        # 去掉未收盘的当前 bar
        cutoff = datetime.utcnow() - timedelta(seconds=tf_sec)
        closed = df[df["date"] <= cutoff]
        if closed.empty:
            closed = df.iloc[:-1] if len(df) > 1 else df

        try:
            if self._code_type == "python":
                sig_intent = self._eval_python_signal(closed, price)
            else:
                sig_intent = self._eval_dsl_signal(closed)
        except Exception as e:
            import traceback
            log.exception(f"[live] 信号计算失败:\n{traceback.format_exc()}")
            self._set_error(f"信号计算失败: {e}")
            return

        if sig_intent is None:
            return
        desired = sig_intent
        self.last_signal = desired
        if desired == 1 and self.position == "flat":
            self._buy(price)
        elif desired == 0 and self.position == "long":
            self._sell_all(price, reason="信号平仓")
        else:
            self._log(f"信号={desired}, 维持 {self.position}")

    def _eval_dsl_signal(self, closed: "pd.DataFrame") -> Optional[int]:
        """DSL: signal_fn(df) -> Series, 取最后值"""
        sig = self._signal_fn(closed)
        val = float(sig.iloc[-1]) if hasattr(sig, "iloc") else float(sig)
        return 1 if val > 0 else 0     # 现货只做多, 负信号压成空仓

    def _eval_python_signal(self, closed: "pd.DataFrame", price: float) -> Optional[int]:
        """Python 策略: 用 on_bar 模拟跑 closed 上的所有 bar, 取最后一次 buy/sell 意图

        简化: 一次性在 closed 上跑完, 收集最后一次 action 决定 desired position
        """
        # 拉 ctx_data
        try:
            ctx_info = build_ctx_series(closed, self.symbol, self.timeframe,
                                        self._ctx_tfs, self._ctx_lookback)
        except Exception as e:
            log.warning(f"[live] python ctx 拉取失败: {e}")
            ctx_info = {"ctx_data": {}}

        # 在 closed 上模拟回放
        # 注: 这里直接调 PythonStrategy.run() 一次, 拿 final position 意图
        # 但 run() 会跑完整 K 线, 包括历史 bar, 状态会推到最新
        try:
            result = self._py_runner.run(
                closed, capital=self._py_capital,
                primary_symbol=self.symbol, primary_timeframe=self.timeframe,
                ctx_data=ctx_info["ctx_data"],
            )
        except Exception as e:
            import traceback
            log.exception(f"[live] python 策略执行失败:\n{traceback.format_exc()}")
            self._set_error(f"Python 策略执行失败: {e}")
            return None

        # 拿最后一次 action 决定 desired
        actions = result.get("actions") or []
        # 关键: 保留 state 以便后续 tick 继续累计, 但合并 _last_error
        prev_state = self._py_state or {}
        new_state = result.get("final_state") or {}
        prev_state.update(new_state)
        self._py_state = prev_state
        if not actions:
            self._log("Python 策略无任何交易意图, 维持当前")
            return None
        last = actions[-1]
        last_action = last.get("action")
        # desired: 1 = 多 (持仓), 0 = 空仓
        # buy 表示希望加仓, sell_all 表示清仓
        # 我们以最终状态为准: last bar 后是 buy/sell/sell_all
        if last_action == "sell":
            return 0
        if last_action == "sell_all":
            return 0
        if last_action == "buy":
            # 模拟盘只能跟随 (要么 flat→long, 要么 long 加仓)
            # 简化: buy 就转 long (不区分加仓, 现货也没法真加仓, 实际还是按 full balance 重买)
            return 1
        return None

    # ---- 下单 ----
    def _buy(self, price: float):
        client = get_demo_client()
        if price <= 0:
            price = self._current_price()
        if price <= 0:
            self._log("无有效价格, 跳过买入")
            return
        free_usdt = self._free("USDT")
        cap = min(self.position_size, float(sys_config.get("trading.max_total_pct", 0.95) or 0.95))
        spend = free_usdt * cap
        filt = client.symbol_filters(self.symbol)
        qty = _floor_qty(spend / price, filt.get("market_step_str"))
        min_notional = filt.get("min_notional") or 0
        min_qty = filt.get("min_qty") or 0
        if qty <= 0 or (min_qty and qty < min_qty) or (min_notional and qty * price < min_notional):
            self._log(f"跳过买入: 可用 {free_usdt:.2f} USDT, 目标额 {spend:.2f} 低于最小名义额/数量")
            return
        res = client.place_order(self.symbol, "BUY", "MARKET", qty)
        executed = float(res.get("executedQty") or qty)
        quote = float(res.get("cummulativeQuoteQty") or 0)
        fill = (quote / executed) if executed > 0 and quote > 0 else price
        self.position = "long"
        self.entry_price = fill
        self.qty = executed
        self._audit("buy", fill, executed, 0, f"策略实盘买入 #{res.get('orderId')}")
        self.last_action = f"买入 {executed} @ {fill:.4f}"
        self._log(self.last_action)

    def _sell_all(self, price: float, reason: str = ""):
        client = get_demo_client()
        base = _base_asset(self.symbol)
        free = self._free(base)
        filt = client.symbol_filters(self.symbol)
        qty = _floor_qty(free, filt.get("market_step_str"))
        if qty <= 0:
            self.position = "flat"
            self.entry_price = 0.0
            self.qty = 0.0
            self._log(f"无持仓可平 ({reason})")
            return
        res = client.place_order(self.symbol, "SELL", "MARKET", qty)
        executed = float(res.get("executedQty") or qty)
        quote = float(res.get("cummulativeQuoteQty") or 0)
        fill = (quote / executed) if executed > 0 and quote > 0 else (price or self._current_price())
        pnl = (fill - self.entry_price) * executed if self.entry_price > 0 else 0.0
        self._audit("sell", fill, executed, pnl, f"策略实盘平仓 {reason} #{res.get('orderId')}")
        self.position = "flat"
        self.entry_price = 0.0
        self.qty = 0.0
        self.last_action = f"平仓 {executed} @ {fill:.4f} ({reason})"
        self._log(self.last_action)

    def _audit(self, side: str, price: float, amount: float, pnl: float, note: str):
        try:
            crud.insert_trade(mode="simulation", symbol=self.symbol, side=side,
                              price=price, amount=amount, pnl=pnl, note=note)
        except Exception as e:
            log.warning(f"[live] 本地审计写入失败 (不影响交易): {e}")


_trader: Optional[LiveTrader] = None


def get_live_trader() -> LiveTrader:
    global _trader
    if _trader is None:
        _trader = LiveTrader()
    return _trader
