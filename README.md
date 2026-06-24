# K7Quant ⚡ 币安加密货币量化回测系统

完整的加密货币量化回测平台，基于 Binance 公开 API，支持多策略、多周期、可视化回测、可编辑配置、自定义 DSL 策略。

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Vue](https://img.shields.io/badge/Vue-3-green) ![Naive UI](https://img.shields.io/badge/UI-Naive-blueviolet) ![License](https://img.shields.io/badge/license-MIT-brightgreen)

## ✨ 核心特性

- 📊 **9 种内置策略**：8 种 DSL (双均线/RSI/MACD/动量轮动/突破新高/布林带均值回归/量价齐升/ADX 趋势跟随) + **1 种 Python 沙箱** (Martingale 网格)
- ⏱️ **16 种 Binance 官方 K 线周期**：`1s` / `1m` / `3m` / `5m` / `15m` / `30m` / `1h` / `2h` / `4h` / `6h` / `8h` / `12h` / `1d` / `3d` / `1w` / `1M` (Binance 官方白名单,前端统一按类别分组)
- 🔬 **33+ 因子库**：MA / EMA / RSI / MACD / BOLL / KDJ / ATR / OBV / VWAP 等,每因子都有中文说明
- 💎 **25 个 USDT 币种**：BTC/ETH/SOL/BNB 等主流 + 完整元信息 (中英文/分类/市值排名/简介)
- 🛠️ **DSL 自定义策略**：类 Python 表达式,`signal = ...` + 可选止损/止盈/仓位/频率,**实时校验**
- 🐍 **Python 沙箱策略**：`def init()` + `def on_bar(state)`,支持状态/循环/动态仓位 (Martingale/网格/趋势跟踪 等)
- 🕐 **多 timeframe 上下文**：策略可声明 `context_timeframes: ["15m", "1h"]`,DSL 里直接用 `ctx_15m_close` / `ctx_1h_ma20`,Python 用 `ctx.klines(tf, n)` / `ctx.factor()`
- 📊 **多周期对比**：同一策略同时跑 4h/1d/1w 等多周期,曲线叠加对比
- 🎯 **一键扫描**：默认跑活跃池所有币种,按夏普排序,前 3 名奖牌标记
- 📈 **专业图表**：净值曲线 (vs BTC 基准) + K线 + MA7/25/99/BOLL/EMA/成交量叠加
- 🔍 **多条件筛选**：6 个预设场景 + 自定义阈值 + 因子条件构建器
- 💬 **系统日志面板**：顶部 🔔 显示所有 API 调用/错误，方便排查
- ⚙️ **可视化配置中心**：所有参数 (回测/币种/周期/策略) 都在 Web 界面编辑，使用 Naive UI 组件
- 🏷️ **币种库**：按市值排名展示，可点击查看每个币种的详细中文介绍
- 📚 **新手友好**：白话教学 + 6 步量化工作流

## 🚀 快速开始

### 方式 1: 一键安装 (推荐 Windows)

```bash
git clone https://github.com/2754LM/K7Quant.git
cd K7Quant
install.bat        # 自动创建 venv + 安装所有依赖 + 构建前端
start.bat          # 启动服务，自动打开浏览器
```

### 方式 2: 手动安装

```bash
# 1. 后端
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt

# 2. 前端
cd frontend && npm install && npm run build && cd ..

# 3. 启动
python run.py
# 浏览器访问 http://127.0.0.1:8765
```

### 方式 3: Docker (TODO)

### ⚙️ 国内访问 (VPN / 代理) 与 Binance 直连

Binance API 在中国大陆需要走代理，两种方式任选其一：

- **走代理**：「设置 → 数据源 + VPN」填入 HTTP/HTTPS 代理（如 Clash 默认 `http://127.0.0.1:7890`），
  保存后重启生效；也支持环境变量 `HTTP_PROXY` / `HTTPS_PROXY`。
- **直连**：能直接访问 `api.binance.com`（海外或已全局代理）则保持「启用代理 = 否」即可，无需任何配置。

在「💾 数据」页点「测试连接」可确认当前是直连还是走代理、是否连通。

### 🧪 模拟盘 (Binance Demo Mode)

「💱 交易」页接入 Binance 模拟交易沙盒（`demo-api.binance.com`），可用虚拟资金真实下单/撤单、查询余额与委托。

1. 登录 Binance → **模拟交易** → **API 密钥管理** → 创建 API 密钥。
2. 复制 `.env.example` 为 `.env`，填入密钥（`.env` 已被 git 忽略，**切勿提交真实密钥**）：
   ```bash
   cp .env.example .env
   # 填入 BINANCE_DEMO_API_KEY / BINANCE_DEMO_API_SECRET
   ```
   也可直接用环境变量：`export BINANCE_DEMO_API_KEY=... BINANCE_DEMO_API_SECRET=...`
3. 确保「设置 → 交易」的模式为 `simulation`（模拟盘），重启后端。
4. 打开「交易」页，状态条显示「已连接沙盒账户」即可下单。国内访问 demo 端点同样走上面的代理配置。

> ⚠️ 模拟盘行情与正式盘相似但**不等同真实行情**，沙盒里有效的策略在正式所未必有效。本期仅 REST，**实盘模式暂不支持**。

## 📁 项目结构

```
K7Quant/
├── README.md / AGENTS.md / LICENSE
├── config.yaml                 # ⚙️ 主配置 (UI 可编辑, 根目录单文件)
├── pyproject.toml              # 🐍 Python 项目元数据 + 依赖 (SQLAlchemy, FastAPI...)
├── requirements.txt            # 同步镜像
│
├── backend/                    # 🌐 FastAPI 后端
│   ├── app.py                  # 入口: lifespan + 路由注册 + 静态前端
│   ├── models.py               # 🗄️ SQLAlchemy ORM 模型 (Symbol/Strategy/Factor/...)
│   ├── api/                    # API 路由层 (按域拆分, 薄编排)
│   │   ├── backtest_api.py     # /api/backtest/*
│   │   ├── factor_api.py       # /api/factor/*
│   │   ├── strategy_api.py     # /api/strategy/*
│   │   ├── data_api.py         # /api/data/*
│   │   ├── symbol_api.py       # /api/symbol/*
│   │   ├── config_api.py       # /api/config/*
│   │   ├── trade_api.py        # /api/trade/* (占位)
│   │   └── rule_api.py         # /api/rule/* (自定义规则)
│   ├── services/               # 业务层 (编排 models + domain)
│   │   ├── backtest_service.py
│   │   ├── factor_service.py
│   │   ├── strategy_service.py
│   │   ├── symbol_service.py
│   │   ├── data_service.py
│   │   ├── trade_service.py
│   │   └── config_service.py
│   ├── core/                   # 基础设施 (config + logger + paths + db engine)
│   ├── data/                   # 数据层 (fetcher + cache + access)
│   ├── factor/                 # 因子库 (33+ 预置因子 + 自动注册)
│   ├── strategy/               # DSL 引擎 + Python 沙箱 + 9 个内置策略 (DSL×8 + Python×1)
│   ├── backtest/               # Backtester + compute_metrics + 绘图
│   └── storage/                # 兼容层 (旧 crud/db 的别名, 新代码用 models)
│
├── frontend/                   # 🎨 Vue3 前端
│   └── src/
│       ├── App.vue             # 根布局 (Naive UI Provider + Tab 路由 + 系统日志)
│       ├── main.js             # 入口 (注册 Naive UI)
│       ├── api/index.js        # axios 封装 + 系统日志自动记录
│       ├── components/         # 可复用组件 (Naive UI 优先)
│       │   ├── DateRangePicker.vue    # n-date-picker + 快捷区间
│       │   ├── TimeframePicker.vue    # 分组按钮 (分/时/天/周 + 自定义)
│       │   ├── StrategyPicker.vue
│       │   ├── MetricCard.vue
│       │   ├── HelpTip.vue
│       │   ├── StateView.vue          # loading/error/empty 三态
│       │   ├── RuleBuilder.vue        # 因子条件构建器 (字段+算子+值)
│       │   ├── SystemLogPanel.vue     # 顶部 🔔 系统日志面板
│       │   ├── LoadingOverlay.vue     # 浮层加载动画
│       │   └── MonacoEditor.vue       # Monaco 代码编辑器
│       ├── views/              # 10 个页面
│       │   ├── Dashboard.vue   # 智能回测 + 多周期对比 + 自定义代码面板
│       │   ├── KLine.vue       # K线 + 多指标 (MA/EMA/BOLL/成交量)
│       │   ├── Factor.vue      # 因子 (单/多/全部/跨币种排名)
│       │   ├── Filter.vue      # 币种筛选 (6 预设 + 自定义)
│       │   ├── Symbols.vue     # 币种库 (25 个币种)
│       │   ├── Strategy.vue    # 策略编辑器 (DSL + Monaco 双模式)
│       │   ├── DataPanel.vue   # 数据缓存
│       │   ├── Trade.vue       # 模拟/实盘 (占位)
│       │   ├── Settings.vue    # 设置 (5 tab, Naive UI)
│       │   └── Learn.vue       # 教程
│       └── utils/
│           └── systemLog.js    # 全局日志服务 (reactive)
│
├── .vscode/
│   └── launch.json             # 🔧 VSCode 一键启动 (Backend + Frontend + Full Stack)
├── .idea/runConfigurations/    # 🔧 PyCharm/IntelliJ run configurations
├── run.py                      # 一键启动 (读 config.yaml 端口)
├── install.bat / start.bat     # Windows 脚本
├── requirements.txt
└── .gitignore
```

> 运行时数据 (`data/`、`*.db`、`frontend/dist/`、`logs/`) 都被 `.gitignore` 忽略；
> 数据库是 SQLite `data/k7quant.db`，首次启动自动建表。

## 🎯 功能页面

| 页面 | 功能 |
|------|------|
| **🎯 智能回测** | 选策略 + K线 + 币种 + 区间 → 一键扫描。多周期对比模式叠加显示。自定义代码面板支持 DSL 编写 + 实时校验 + 保存为策略 |
| **📊 K线数据** | 顶部币种中文介绍，下方 K线图 (蜡烛 + MA7/25/99 + 成交量副图) + 数据表切换。带 🔄 刷新按钮 |
| **🔬 因子** | 4 个 tab: 单因子查询 / 多因子相关性 (chip 选择) / 全部因子 (并行算所有) / 跨币种排名 |
| **🔍 币种筛选** | 6 个预设场景 + 多条件自定义。Naive UI 下拉 |
| **💎 币种库** | 25 个币种按市值排名，可点击查看详细描述/标签/分类。多选切换活跃池 |
| **💾 数据缓存** | 按时间帧分组管理，统计占用 |
| **⚙️ 设置** | 5 个 tab: 回测默认值 / 数据源+VPN / 界面主题 / 交易 / 关于。使用 Naive UI 组件 |
| **📚 量化课堂** | 9 指标卡片 + 8 概念 + 6 步工作流 |

## 📡 API 列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 (含 Binance 连通性) |
| GET | `/api/config` | 完整配置 (settings/symbols/strategies/timeframes/active_symbols) |
| PUT | `/api/config/backtest` | 回测默认值 |
| PUT | `/api/config/data-source` | 数据源 + 代理 |
| PUT | `/api/config/ui` | 主题 / 问号提示 |
| PUT | `/api/config/trading` | 模拟/实盘参数 |
| GET | `/api/trade/connectivity` | 模拟盘连通性 + 凭据校验 |
| GET | `/api/trade/account` | 模拟盘账户余额 (签名) |
| GET | `/api/trade/open-orders?symbol=` | 当前委托 (签名) |
| POST | `/api/trade/order` | 下单 (签名) |
| DELETE | `/api/trade/order?symbol=&order_id=` | 撤单 (签名) |
| GET | `/api/trade/my-trades?symbol=` | 成交历史 (签名) |
| POST | `/api/backtest/single` | 单标的回测 |
| POST | `/api/backtest/scan` | 池子扫描 |
| POST | `/api/backtest/code` | 用临时 DSL 代码回测 |
| POST | `/api/backtest/filter` | 币种筛选 |
| GET | `/api/backtest/kline/{symbol}` | K线 + MA + 统计 |
| GET/POST/DELETE | `/api/factor/*` | 因子查询/计算/相关性/排名 |
| GET/POST/DELETE | `/api/strategy/*` | 策略 CRUD/校验/模板/DSL 文档 |
| GET/POST/DELETE | `/api/symbol/*` | 币种元信息/活跃池 |
| GET/POST/DELETE | `/api/rule/*` | 自定义规则/查询 |
| GET | `/api/data/cache` | 列出缓存 |
| DELETE | `/api/data/cache?tf=&symbol=` | 删除缓存 |
| POST | `/api/data/fetch` | 触发下载 |

## 📊 内置策略

### DSL 策略 (表达式型)

| ID | 名称 | 类型 | 适合 |
|----|------|------|------|
| `双均线交叉` | MA(7) 上穿 MA(25) | trend | 趋势市 |
| `RSI 超买超卖` | RSI(14) < 30 买入 | mean_reversion | 震荡市 |
| `MACD 金叉死叉` | EMA(12) > EMA(26) | trend | 中长线 |
| `动量轮动` | N 根涨幅 > 0 | momentum | 牛市 |
| `突破新高` | high_break + MA 过滤 | breakout | 突破 |
| `布林带均值回归` | zscore < -2 | mean_reversion | 反转 |
| `量价齐升` | volume + MA 配合 | volume | 异动 |
| `ADX 趋势跟随` | MA 交叉 + ADX > 25 | trend | 强趋势 |
| `多周期共振 (15m+1h)` | `ctx_15m_close > ctx_15m_ma20 AND ctx_1h_close > ctx_1h_ma20` | trend | 大级别共振 |

### Python 沙箱策略 (有状态型)

| ID | 名称 | 说明 |
|----|------|------|
| `Martingale 网格` | 价格跌 1% 加倍仓位,涨回去止盈 | 适合震荡市低吸,演示 `state` / `buy()` / `sell_all()` 用法 |

## 🛠️ DSL 策略编写

### DSL 表达式策略 (简单/无状态)

```python
# 双均线交叉示例
signal = CROSS_UP(MA(close, 7), MA(close, 25)) AND NOT CROSS_DOWN(MA(close, 7), MA(close, 25))
止损 = 0.05      # 5% 止损 (写 0 表示不设止损)
止盈 = 0.15      # 15% 止盈
仓位 = 1.0       # 满仓
```

支持的因子函数：`MA / EMA / RSI / MACD / BOLL / KDJ / momentum / volatility / high_break / low_break / obv / vwap / mfi / adx / atr / ...`（共 33+）

支持的逻辑：`AND / OR / NOT / CROSS_UP / CROSS_DOWN`，比较运算符 `> < >= <= == !=`

**安全**: AST 白名单解释执行，禁止 eval/属性访问/下标。

### Python 沙箱策略 (有状态)

适用场景：Martingale/网格/动态仓位/跨 bar 状态 等需要状态的策略。代码类型 `python`，模板内置。

```python
def init():
    """可选：返回初始 state dict (跨 bar 持久化)"""
    return {"entry": 0.0, "qty": 0.0, "grids": 0}

def on_bar(state):
    """必填：每根 K 线调用一次"""
    p = ctx.now()        # 当前 close
    if ctx.position() > 0 and p < state["entry"] * 0.99 and state["grids"] < 5:
        # 价格跌 1% 加倍仓,最多 5 次
        state["entry"] = p
        state["qty"] = ctx.position() * 2
        state["grids"] += 1
        buy(state["qty"])
    elif ctx.position() > 0 and p > state["entry"] * 1.02:
        # 涨 2% 全平
        sell_all()
```

**沙箱 globals**：`pd / np / math / json / datetime / ctx / state / buy(usdt) / sell(coin_qty) / sell_all() / cash() / equity() / position()`

**安全**：AST 白名单拒绝 `import / async / dunder / open / exec / eval / getattr / setattr`。单 bar 抛错只跳过该 bar。

### 多 timeframe 上下文 (DSL + Python 都支持)

策略可声明 `context_timeframes: ["15m", "1h"]` + `context_lookback: 20`。系统自动拉取这些 tf 的 K 线,计算到主 bar 截止时间的最新值与统计量。

**DSL 里直接用**：

```python
# 主图 5m + 上下文 15m / 1h
signal = (ctx_15m_close > ctx_15m_ma20)              # 15m 站上 ma20
        AND (ctx_1h_close > ctx_1h_ma20)              # 1h 也站上 ma20
        AND (close > MA(close, 25))                   # 主图 5m 站上 ma25
止损 = 0.05
```

自动生成的变量（每个 tf × 每个 col × 每个统计）：
- `ctx_<tf>_close / open / high / low / volume` — 截至主 bar 时间的最新值
- `ctx_<tf>_ma20 / max20 / min20 / std20 / sum20` — 最近 20 根的统计 (lookback 可调)

**Python 里通过 ctx**：

```python
def on_bar(state):
    df15 = ctx.klines("15m", 20)            # 最近 20 根 15m K 线 (截至当前 bar)
    close15 = ctx.series("15m", "close", 20) # 同上,只取 close 列
    ma20 = ctx.ref_tf("15m", "close", 20).mean()
    macd = ctx.factor("macd", "15m", 20)    # 在 15m 上跑 MACD 因子
    if ctx.now_tf("15m") > ma20:
        buy(100)
```

**适用场景**：大级别共振 / 多周期趋势确认 / 跨周期套利 / 减少假突破 等。

## 🛠️ 技术栈

- **后端**: FastAPI + Uvicorn + SQLAlchemy 2.0 ORM + Pydantic + PyYAML
- **前端**: Vue 3 + Vite + ECharts + **Naive UI** + Axios
- **数据**: Binance Spot API (无需 Key)
- **计算**: pandas + numpy + matplotlib
- **存储**: SQLite (`data/k7quant.db`) + 完整 ORM 模型 (`backend/common/models.py`)
- **配置**: 根目录 `config.yaml` (UI 可编辑) + `pyproject.toml` (Python 依赖)
- **编辑器**: Monaco (策略代码) + 表达式编辑器双模式

## 🛠️ IDE 集成

**VSCode / Cursor**: 打开项目后, F5 选择「Full Stack」一键启动前后端
- 详见 `.vscode/launch.json`

**PyCharm / IntelliJ IDEA**: 右上角运行配置下拉选择
- `Backend: FastAPI Dev` (uvicorn --reload)
- `Frontend: Vite Dev` (npm run dev)
- `Full Stack (Backend+Frontend)` (同时启动两个)
- 详见 `.idea/runConfigurations/`

**命令行**:
```bash
# 后端 (热更新)
uvicorn backend.app:app --reload --host 127.0.0.1 --port 8765

# 前端 (热更新)
cd frontend && npm run dev
```

## 📦 扩展指南

- **加策略**: `backend/core/strategy/__init__.py` 的 `BUILTIN_STRATEGIES` 加一条, 重启自动写入 DB
- **加因子**: `backend/core/factor/__init__.py` 写 `f_xxx(df, **p)` + 在 `_FACTORS` 注册
- **加表/字段**: `backend/common/models.py` 加 ORM 类, 重启自动 `create_all` (SQLAlchemy 自动迁移)
- **加 API**: `backend/api/xxx_api.py` 加 endpoint + `app.py` `include_router`
- **加页面**: `frontend/src/views/xxx.vue` + `App.vue` 的 `TABS` 注册

## ⚠️ 免责声明

本项目仅供**研究学习**，不构成任何投资建议。加密货币投资风险极高，过往表现不代表未来，请勿投入无法承受损失的资金。

## 📄 License

MIT
