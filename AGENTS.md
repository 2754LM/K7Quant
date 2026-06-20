# K7Quant - AI Agent 工作指南

帮助 AI Agent (Claude/Cursor/Copilot 等) 快速理解项目并高效修改代码。
**本文与实际代码一致 (v4.0)**：后端在 `backend/`，配置是根目录 `config.yaml`，策略是 DSL 表达式。

## 项目一句话总结

基于 Binance 公开 API 的加密货币量化回测系统：FastAPI + Vue3 + SQLite + YAML 配置，
因子库 (30+) + DSL 自定义策略 + 多周期回测。**纯本地单机运行，不要把它部署到公网。**

## 技术栈

- **后端**: Python 3.11 + FastAPI + pandas + numpy + SQLAlchemy-style sqlite3
- **前端**: Vue 3.4 + Vite 5 + ECharts 5 + Naive UI + axios
- **存储**: SQLite (单文件 `data/k7quant.db`)，按 thread-local 连接
- **配置**: YAML (`config.yaml`，路径见 `backend/core/config.py:CONFIG_PATH`)
- **数据源**: Binance 公开 REST API (无需 key，行情数据)

## 项目结构

```
D:\Desktop\lh\
├── backend/                  # Python 后端 (FastAPI)
│   ├── api/                  # 路由层 (薄编排, 业务逻辑放 services/)
│   │   ├── __init__.py
│   │   ├── backtest_api.py   # /api/backtest/*
│   │   ├── config_api.py     # /api/config/*
│   │   ├── data_api.py       # /api/data/*
│   │   ├── factor_api.py     # /api/factor/*
│   │   ├── rule_api.py       # /api/rule/*
│   │   ├── strategy_api.py   # /api/strategy/*
│   │   ├── symbol_api.py     # /api/symbol/*
│   │   └── trade_api.py      # /api/trade/*
│   ├── services/             # 业务逻辑层
│   │   ├── backtest_service.py
│   │   ├── config_service.py
│   │   ├── data_service.py
│   │   ├── factor_service.py
│   │   ├── helpers.py
│   │   ├── strategy_service.py
│   │   ├── symbol_service.py
│   │   └── trade_service.py
│   ├── storage/              # 数据访问
│   │   ├── db.py             # SQLite schema + 连接
│   │   └── crud.py           # CRUD 操作
│   ├── factor/__init__.py    # 33+ 因子 (MA/EMA/RSI/MACD/...)
│   ├── strategy/__init__.py  # 8 个内置策略 + DSL 引擎
│   ├── backtest/__init__.py  # Backtester + compute_metrics
│   ├── data/                 # 数据下载/缓存/访问
│   │   ├── fetcher.py        # Binance REST 客户端
│   │   ├── cache.py          # 本地 CSV 缓存
│   │   └── access.py         # 缓存优先
│   ├── core/
│   │   ├── __init__.py       # 路径常量 (ROOT/DATA_DIR/...)
│   │   ├── config.py         # YAML 配置加载/保存
│   │   └── logger.py         # 日志
│   └── app.py                # FastAPI 入口, 挂载 router
├── frontend/                 # Vue3 前端
│   └── src/
│       ├── api/index.js      # axios + 全部 API 调用
│       ├── components/       # 复用组件
│       │   ├── DateRangePicker.vue    # 区间选择 (快捷按钮 + HTML5 date)
│       │   ├── TimeframePicker.vue    # 视觉化 TF 选择 (分钟/小时/天/周)
│       │   ├── StrategyPicker.vue
│       │   ├── MetricCard.vue
│       │   ├── HelpTip.vue
│       │   ├── StateView.vue          # loading/error/empty 三态
│       │   ├── RuleBuilder.vue        # 因子条件构建器
│       │   └── SystemLogPanel.vue     # 顶部 🔔 系统日志面板
│       ├── views/             # 页面 (10 个 Tab)
│       │   ├── Dashboard.vue  # 智能回测 + 多周期 + 自定义代码
│       │   ├── KLine.vue      # K线图 + 多指标
│       │   ├── Factor.vue     # 因子 (单/多/全部)
│       │   ├── Filter.vue     # 币种筛选
│       │   ├── Symbols.vue    # 币种库
│       │   ├── Strategy.vue   # 策略编辑器
│       │   ├── DataPanel.vue  # 数据缓存
│       │   ├── Trade.vue      # 模拟/实盘 (占位)
│       │   ├── Settings.vue   # 设置
│       │   └── Learn.vue      # 教程
│       ├── utils/
│       │   └── systemLog.js  # 全局日志服务 (reactive)
│       ├── App.vue            # 根 (Naive UI Provider + Tab 路由)
│       ├── main.js            # 入口 (app.use(naive))
│       └── style.css          # 全局 CSS 变量 (Binance 暗色主题)
├── config.yaml               # 用户配置 (host/port/proxy/...)
├── data/                      # 运行时数据 (DB + 缓存, 已 gitignore)
│   ├── k7quant.db            # SQLite
│   └── cache/{tf}/{symbol}.csv
├── logs/                      # 运行时日志 (已 gitignore)
├── run.py                    # 启动入口 (FastAPI)
├── start.bat                 # Windows 一键启动
├── install.bat                # Windows 一键安装
├── requirements.txt
└── README.md
```

## 关键文件位置 (改哪里查哪里)

| 想改什么 | 必读/必改文件 |
|---------|--------------|
| 加内置策略 | `backend/strategy/__init__.py` 的 `BUILTIN_STRATEGIES` 数组 |
| 改策略 DSL 引擎 | `backend/strategy/__init__.py` 的 `StrategyEngine` (compile/_parse/_build_signal_fn) |
| 加因子 | `backend/factor/__init__.py` 写 `f_xxx(df, **p)` + 在 `_FACTORS` 列表注册 |
| 改回测逻辑 | `backend/backtest/__init__.py` (`Backtester.run` / `compute_metrics`) |
| 改配置项 | `config.yaml` + `backend/core/config.py` 的 `DEFAULTS` + 前端 `Settings.vue` |
| 加币种元信息 | `backend/services/symbol_service.py` 的 `DEFAULT_SYMBOLS` 或 `/api/symbol/upsert` |
| 改 API 路由 | `backend/api/*_api.py` + `backend/app.py` `include_router` |
| 改业务逻辑 | `backend/services/*.py` (与 router 解耦) |
| 改数据下载/缓存 | `backend/data/fetcher.py` / `cache.py` / `access.py` |
| 改前端页面 | `frontend/src/views/` + `App.vue` 的 `TABS` 注册 |
| 改前端样式 | `frontend/src/style.css` (含 `[data-theme="light"]`) + 各 `.vue` 的 `<style scoped>` |
| 改顶层 Tab | `frontend/src/App.vue` 的 `TABS` 数组 |
| 加新 API 调用 | `frontend/src/api/index.js` 加 export, 在视图中 import |
| 改顶部状态/日志 | `frontend/src/App.vue` + `frontend/src/components/SystemLogPanel.vue` |
| 改因子输入控件 | `frontend/src/components/RuleBuilder.vue` |
| 改日期/时间选择 | `frontend/src/components/DateRangePicker.vue` / `TimeframePicker.vue` |

## API 一览

`/api/config` (GET) - 配置: `{ settings, symbols, strategies, timeframes, active_symbols }`
`/api/health` (GET) - 健康检查
`/api/factor/list` (GET) - 因子列表
`/api/factor/compute` (POST) - 单因子
`/api/factor/compute-many` (POST) - 批量
`/api/factor/correlate` (POST) - 相关性
`/api/factor/rank` (POST) - 跨币种排名
`/api/strategy/list` (GET) - 策略列表
`/api/strategy/{id}` (GET) - 策略详情
`/api/strategy/create|update|delete` (POST) - CRUD
`/api/strategy/templates` (GET) - 模板
`/api/strategy/dsl-docs` (GET) - DSL 文档
`/api/strategy/validate` (POST) - 代码验证
`/api/backtest/single` (POST) - 单币回测
`/api/backtest/scan` (POST) - 池扫描
`/api/backtest/code` (POST) - 用代码回测
`/api/backtest/filter` (POST) - 筛选
`/api/backtest/kline/{symbol}` (GET) - K线 + MA + 统计
`/api/backtest/runs` (GET) - 历史回测
`/api/symbol/list` (GET) - 币种列表
`/api/symbol/{s}` (GET) - 币种详情
`/api/symbol/upsert` (POST) - 新增/更新
`/api/symbol/active` (POST) - 设置活跃池
`/api/symbol/active/current` (GET) - 当前活跃
`/api/data/cache` (GET) - 缓存状态
`/api/data/cache` (DELETE) - 清理缓存
`/api/data/exchange-symbols` (GET) - Binance 全部 USDT
`/api/data/test-connection` (GET) - 连接测试
`/api/data/fetch` (POST) - 触发下载
`/api/rule/list` (GET) - 自定义规则
`/api/rule/create` (POST) - 新建规则
`/api/rule/{id}` (DELETE) - 删除规则
`/api/trade/status|trades|record` - 交易 (占位)
`/api/config/backtest|data-source|ui|trading` (PUT) - 更新设置

## 关键设计

### 策略 DSL (`backend/strategy/__init__.py`)

策略是一段 DSL 文本，存在 `BUILTIN_STRATEGIES` 数组或 DB `strategies` 表：

```python
{
    "name": "双均线交叉",
    "description": "MA7 上穿 MA25 买入",
    "category": "trend",       # trend / mean_reversion / momentum / breakout / volume / custom
    "code": """signal = CROSS_UP(MA(close, 7), MA(close, 25)) AND NOT CROSS_DOWN(MA(close, 7), MA(close, 25))
止损 = 0.05
止盈 = 0.15
仓位 = 1.0""",
    "params_schema": {"ma_short": {"label": "短均线", "type": "int", "default": 7, "min": 2, "max": 60}}
}
```

`StrategyEngine.compile(code, params)` 流程:
1. `_parse(code)` - 用正则匹配 `signal/止损/止盈/仓位/频率`
2. 提取 `signal` 表达式
3. `replace_cols()` - `close` → `_df["close"]`
4. `replace_calls()` - `MA(close,7)` → `_get("MA", "close,7")` → 函数调用
5. `replace_logic()` - `AND/OR` → `&/|`, `NOT` → `~`
6. `exec()` 在沙箱里执行, 暴露 `_df` + 因子函数

**安全**: AST 白名单 + 禁止属性访问 + 禁止下标。没有 `eval`。

### 因子系统 (`backend/factor/__init__.py`)

33+ 因子 (MA/EMA/RSI/MACD/BOLL/KDJ/ATR/ADX/OBV/VWAP/...)：
- 写函数 `f_xxx(df, **params) -> Series or DataFrame`
- 加到 `_FACTORS` 列表自动注册到 `FACTOR_REGISTRY`
- `_FACTORS` 元素: `(id, name_zh, name_en, category, formula, description, params_schema)`

### 关键约定

- **API 响应格式**: 全部 `{ "data": ... }` 或 `{"error": "..."}` (单端点可两种)
- **前端 cfg 结构**: `cfg.value = { settings: {...}, symbols: [...], strategies: [...], timeframes: [...], active_symbols: [...] }`
- **顶部 🔔**: SystemLogPanel 自动收集 API 调用日志, 错误用红色 badge 角标提示
- **Naive UI**: 已在 `main.js` 注入, 用 `n-select`/`n-input-number`/`n-button`/`n-tag` 替换原生元素
- **主题**: `[data-theme="dark"|"light"]` 切换, CSS 变量定义在 `style.css:23-38`
- **ECharts 重用**: `getOrInitChart(id)` 检查 `chart.getDom() !== el` 决定是否 dispose + 重新 init

## 代码规范

### Python
- 缩进 4 空格；import 顺序：标准库 → 第三方 → 本地
- 函数参数/返回值带类型提示；模块/类/公开函数写 docstring
- 单文件尽量 < 500 行
- 中文注释可以 (项目对外是中文)

### Vue
- Composition API + `<script setup>`；prop 用 `defineProps`、事件用 `defineEmits`
- 全局样式 `style.css`，组件私有样式 `<style scoped>`，颜色用 CSS 变量
- 复杂交互用 Naive UI 组件 (`n-select` 带搜索, `n-input-number` 步进, `n-tag` 标签)
- API 错误用 `useMessage()` toast, 不要用 `alert()`
- 表单交互要给视觉反馈 (loading 状态, 按钮 disabled 条件)

## 添加新策略 (DSL)

在 `backend/strategy/__init__.py` 的 `BUILTIN_STRATEGIES` 数组加一条，然后重启后端，会自动写入 DB (见 `strategy_service.init_builtin_strategies()`)。

## 添加新 API 端点

1. 在对应 `backend/api/xxx_api.py` 加 endpoint（业务逻辑放 `services/`，router 只编排）：
2. 新域则新建 `backend/api/my_api.py`，在 `backend/api/__init__.py` 导出，再到 `backend/app.py` 挂载
3. 前端在 `frontend/src/api/index.js` 加 export
4. 视图中 import 并调用

## 修改配置项

1. `backend/core/config.py` 的 `DEFAULTS` 加字段
2. `backend/api/config_api.py` 对应 Request 模型加字段
3. 前端 `Settings.vue` 加表单 (用 `n-input-number`/`n-select`) + 保存调用
4. 启动时已在 `init_builtin_strategies()` 等处自动初始化

## 添加新因子

```python
# 1. 写函数
def f_new_factor(df, period: int = 14) -> pd.Series:
    return df["close"].rolling(period).std() * 100

# 2. 加到 _FACTORS 列表
("new_factor", "新因子", "New", "统计类", "公式",
 "中文说明", {"period": {"label": "周期", "type": "int", "default": 14, "min": 2, "max": 100}})

# 3. 重启后端, 自动注册到 FACTOR_REGISTRY
```

## 调试技巧

```bash
# 后端 (无需起 server)
python -c "from backend.services.backtest_service import scan_pool; print(scan_pool(1))"

# 起服务
python run.py            # 读 config.yaml 的端口, 默认 http://127.0.0.1:8765

# 前端 dev (热更新, vite 代理 /api -> 8765)
cd frontend && npm run dev
# 生产构建
cd frontend && npm run build    # 产物 frontend/dist, FastAPI 自动 serve

# API 自测
curl http://127.0.0.1:8765/api/health
curl http://127.0.0.1:8765/api/config | python -m json.tool
curl http://127.0.0.1:8765/api/factor/list | python -m json.tool
```

## 常见陷阱

1. **配置文件是根目录 `config.yaml`**（不是 `config/settings.yaml`）。
2. **DB 是 SQLite** `data/k7quant.db`；连接每线程独立，写操作走 `transaction()`。
3. **`data/`、`*.db`、`frontend/dist/`、`logs/` 都被 .gitignore**；`backend/data/` 是源码包，不要误删。
4. **CORS 只放行本机来源**；不要为了图方便改回 `allow_origins=["*"]`（曾导致安全问题）。
5. **DSL 不要用 eval**；扩展语法请改 `StrategyEngine`（AST 白名单），保持安全。
6. **YAML/文件读写统一 `encoding="utf-8"`**；Binance fetcher 自带限速，不要去掉。
7. **ECharts 实例**: 切换页面后再切回, 用 `getOrInitChart()` 检测并 dispose+重新 init, 否则旧实例画在 detached DOM 上看不到。
8. **Naive UI 消息**: 在子组件中需用 `inject('n-message-provider')` 或 `useMessage()` (后者需在 `<n-message-provider>` 内部使用)。简单场景用全局 toast 也行。
9. **时间格式**: 前后端统一 YYYYMMDD (8 位字符串)。DateRangePicker 自动转换 HTML5 的 YYYY-MM-DD。
10. **改了后端要重启**: `pythonw` 启动的进程不会热加载 Python 模块。

## 安全须知 (重要)

本项目以本地桌面形式分发（打包 EXE / `start.bat`）。请始终保持：
- CORS 仅本机来源；服务绑定 `127.0.0.1`
- DSL 走 AST 白名单（禁止 `eval` / 属性访问 / 下标）
- 静态文件 serve 做目录穿越防护
- 不暴露任何 API key / 凭证到前端

## Bug 报告 / 改进建议

GitHub Issues: https://github.com/2754LM/K7Quant/issues
