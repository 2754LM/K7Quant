# K7Quant 架构详解

## 分层架构

```
┌────────────────────────────────────────────────────────┐
│  Frontend (Vue 3 + Vite + ECharts)                     │
│  - views/   页面级组件                                 │
│  - components/  通用组件                              │
│  - api/      axios HTTP 封装                          │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTP/JSON (CORS)
┌──────────────────────────▼─────────────────────────────┐
│  Backend (FastAPI)                                     │
│  - routers/   API 路由层 (按域拆分)                    │
│  - services/  业务层 (编排 core + 业务规则)            │
└──────────────────────────┬─────────────────────────────┘
                           │ 直接调用
┌──────────────────────────▼─────────────────────────────┐
│  quant_core (核心库，与 UI/网络 0 耦合)                │
│  - settings.py   配置加载 (YAML + 单例 + 锁)          │
│  - data/         数据访问 (Fetcher + Cache)           │
│  - strategies/   策略实现 (基类 + 4 个策略)            │
│  - backtest/     回测引擎 + 指标                       │
└────────────────────────────────────────────────────────┘
```

## 数据流

### 单标的回测

```
User  → Dashboard.vue
     → scanPool(params)              [api/index.js]
     → POST /api/backtest/scan        [routers/backtest.py]
     → scan_pool(...)                [services/backtest_service.py]
     → get_many(symbols)             [data/access.py]
     → get_kline(symbol, tf)         [data/access.py]
     → BinanceFetcher.fetch()        [data/fetcher.py]
     → DataCache.read/write          [data/cache.py]
     → get_strategy(id).generate(df) [strategies/xxx.py]
     → Backtester.run(signal)        [backtest/engine.py]
     → compute_metrics(result)       [backtest/metrics.py]
     → plot_equity(...)              [backtest/engine.py]
     → return {metrics, equity, chart_base64, ...}
     → Frontend renders
```

### 配置修改

```
User clicks "保存" in Settings.vue
  → setActiveSymbols(symbols)        [api/index.js]
  → PUT /api/config/active-symbols  [routers/config.py]
  → update_active_symbols(list)     [services/config_service.py]
  → update_settings({...})          [settings.py]
     → with _lock:
       → _load_yaml() if cache empty
       → _deep_update(cache, patch)  # 支持点路径
       → _save_yaml(SETTINGS_PATH)
       → reload cache from disk      # 避免残留 key
       → return new cache
  → Frontend receives new settings
```

## 关键设计

### 1. 配置中心化 (`config/settings.yaml`)

所有可变参数都在 YAML 里，**前端可在「配置中心」修改**，后端立即生效。

```yaml
backtest:
  initial_capital: 10000.0
  commission: 0.0004
  leverage: 1
  start_date: "20240101"
  end_date: "auto"
  default_timeframe: "4h"
active_symbols: [BTCUSDT, ETHUSDT, SOLUSDT, ...]
strategy_defaults:
  ma_cross: {ma_short: 7, ma_long: 25}
  rsi: {rsi_period: 14, ...}
```

`settings.py` 提供：
- 单例缓存 (`_settings_cache`)
- 线程锁 (`_lock`)，避免并发写
- 点路径更新 (`{"backtest.commission": 0.0005}`)
- 便捷访问器 (`C.api_base()`, `C.initial_capital()` 等)

### 2. 策略插件化 (`strategies/`)

所有策略继承 `Strategy` 基类，定义 `params_schema` 自动生成前端表单：

```python
class MACross(Strategy):
    id = "ma_cross"
    name = "双均线交叉"
    params_schema = {
        "ma_short": {"label": "短均线", "type": "int", "default": 7, "min": 2, "max": 60},
        "ma_long":  {"label": "长均线", "type": "int", "default": 25, "min": 5, "max": 250},
    }

    def generate(self, df) -> pd.DataFrame:
        # 输出必须包含 date/close/position (0/1)
        ...
```

**新增策略只需 3 步**：
1. 在 `strategies/` 新建文件继承 `Strategy`
2. 实现 `generate()` 方法
3. 在 `strategies/__init__.py` 的 `ALL_STRATEGIES` 中注册

前端会自动显示新策略，无需改前端代码。

### 3. 数据缓存分层

```
Binance API  →  Fetcher  →  Cache (data/{timeframe}/{symbol}.csv)
                                 ↓
                              Access.get_kline()  →  Strategy  →  Engine
```

- 首次访问：API 下载 → 落盘
- 后续访问：直接读 CSV（快 1000x）
- 按 timeframe 分目录，互不干扰

### 4. 路由拆分 (`routers/`)

按业务域拆分，每个 router 一个文件：

| Router | 前缀 | 职责 |
|--------|------|------|
| `backtest.py` | `/api/backtest` | 回测、K线、筛选 |
| `data.py`     | `/api/data`     | 缓存管理 |
| `config.py`   | `/api/config`   | 配置 CRUD |

每个 router 用 `APIRouter(prefix=..., tags=[...])` 注册到 `app.py`。

### 5. 服务层与路由解耦 (`services/`)

路由层只做：
1. 接收 HTTP 请求
2. 解析 Pydantic 模型
3. 调 service
4. 返回响应

业务逻辑都在 service 层（可复用、可单元测试、不依赖 HTTP）。

## 性能考虑

- **缓存**: 首次冷启动后所有数据从本地 CSV 读取
- **分页拉取**: Binance API 单次最多 1000 根，fetcher 自动分页
- **指标计算**: numpy 向量化，无 Python 循环
- **图片**: 返回 base64 编码 PNG（前端直接渲染）
- **图表数据**: 只传最近 500 根，前端渲染用 echarts dataZoom 支持缩放

## 扩展点

| 想加什么 | 改哪里 |
|---------|--------|
| 新策略 | `quant_core/strategies/` 新建文件 + 注册 |
| 新指标 | `quant_core/backtest/metrics.py` 加字段 |
| 新时间帧 | `config/settings.yaml` 加 + `BARS_PER_YEAR` 同步 |
| 新币种 | `config/symbols.yaml` 加元信息 + UI 加进活跃池 |
| 新页面 | `frontend/src/views/` 新建 + `App.vue` 注册 |
| 新 API | `backend/routers/` 新建文件 + `app.py` 注册 |
| 新数据源 | `quant_core/data/fetcher.py` 加新类 |