# K7Quant ⚡ 币安加密货币量化回测系统

完整的加密货币量化回测平台，基于 Binance 公开 API，支持多策略、多周期、可视化回测、可编辑配置。

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Vue](https://img.shields.io/badge/Vue-3-green) ![License](https://img.shields.io/badge/license-MIT-brightgreen)

## ✨ 核心特性

- 📊 **4 种内置策略**：双均线交叉、动量轮动、RSI 超买超卖、MACD 金叉死叉
- ⏱️ **12 种 K 线周期**：1m / 5m / 15m / 1h / 4h / 1d / 1w 等
- 💎 **25 个 USDT 币种**：BTC/ETH/SOL/BNB 等主流 + 完整元信息 (中英文/分类/市值排名/简介)
- 🎯 **一键扫描**：默认跑活跃池所有币种，按夏普排序，前 3 名奖牌标记
- 📈 **专业图表**：净值曲线 (vs BTC 基准) + K线 + MA7/25/99 叠加
- 🔍 **多条件筛选**：6 个预设场景 + 自定义阈值
- ⚙️ **可视化配置中心**：所有参数 (回测/币种/周期/策略) 都在 Web 界面编辑
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

## 📁 项目结构

```
K7Quant/
├── README.md                   # 本文档
├── ARCHITECTURE.md             # 架构详解
├── AGENTS.md                   # AI Agent 工作指南
├── LICENSE                     # MIT 协议
│
├── config/                     # ⚙️ 配置中心 (UI 可编辑)
│   ├── settings.yaml           # 主配置 (回测/服务/时间帧/活跃币种/策略默认)
│   └── symbols.yaml            # 25 个币种的完整元信息
│
├── quant_core/                 # 🧠 核心库 (无 UI 依赖)
│   ├── settings.py             # YAML 配置加载器 (单例 + 线程锁)
│   ├── data/                   # 数据层
│   │   ├── fetcher.py          # Binance API 客户端
│   │   ├── cache.py            # 本地 CSV 缓存 (按时帧分目录)
│   │   └── access.py           # 高层 API: get_kline / get_many
│   ├── strategies/             # 策略层
│   │   ├── base.py             # Strategy 基类
│   │   ├── ma_cross.py         # 双均线
│   │   ├── momentum_rotation.py # 动量轮动 (池子)
│   │   ├── rsi.py              # RSI 超买超卖
│   │   └── macd.py             # MACD 金叉死叉
│   └── backtest/               # 回测引擎
│       ├── engine.py           # Backtester + plot_equity
│       └── metrics.py          # 绩效指标 (Sharpe/Calmar/MaxDD/WinRate...)
│
├── backend/                    # 🌐 FastAPI 服务层
│   ├── app.py                  # 入口
│   ├── routers/                # API 路由 (按域拆分)
│   │   ├── backtest.py         # /api/backtest/*
│   │   ├── data.py             # /api/data
│   │   └── config.py           # /api/config/*
│   └── services/               # 业务层 (调用 core + 编排)
│       ├── backtest_service.py # 单标的/池子/K线/筛选
│       ├── data_service.py     # 缓存查询/清理
│       ├── config_service.py   # 配置读写
│       └── helpers.py          # 通用工具
│
├── frontend/                   # 🎨 Vue3 前端
│   ├── src/
│   │   ├── App.vue             # 根布局 + 路由
│   │   ├── api/index.js        # axios 封装
│   │   ├── components/         # 通用组件
│   │   │   ├── MetricCard.vue
│   │   │   ├── StrategyPicker.vue
│   │   │   ├── TimeframePicker.vue
│   │   │   └── SymbolPicker.vue
│   │   └── views/
│   │       ├── Dashboard.vue   # 智能回测主页
│   │       ├── KLine.vue       # K线 (含币种详情卡)
│   │       ├── Filter.vue      # 币种筛选 (6 个预设)
│   │       ├── Symbols.vue     # 币种库 (按市值排名 + 详情)
│   │       ├── DataPanel.vue   # 数据缓存管理
│   │       ├── Settings.vue    # 配置中心 (5 个 tab)
│   │       └── Learn.vue       # 量化课堂
│   └── dist/                   # 构建产物
│
├── run.py                      # 一键启动
├── install.bat / start.bat     # Windows 脚本
├── build.py                    # PyInstaller 打包
├── requirements.txt
└── .gitignore
```

## 🎯 功能页面

| 页面 | 功能 |
|------|------|
| **🎯 智能回测** | 默认跑活跃池，按夏普排序，前 3 名奖牌。所有参数即时生效 |
| **📊 K线数据** | 顶部显示选中币种的完整中文介绍 + 标签，下方 K线图 + 数据表切换 |
| **🔍 币种筛选** | 6 个预设场景 (牛市赢家/防御币/高夏普/低价/中价/高价) + 多条件自定义 |
| **💎 币种库** | 25 个币种按市值排名，可点击查看详细描述/标签/分类 |
| **💾 数据缓存** | 按时间帧分组管理，可单独删除某个币种或整个时间帧 |
| **⚙️ 配置中心** | 5 个 tab：回测默认值/活跃币种/K线周期/策略参数/关于 |
| **📚 量化课堂** | 8 个指标白话讲解 + 8 个核心概念 + 6 步工作流 + 风险提醒 |

## 📡 API 列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/config` | 获取完整配置 (settings + symbols + strategies) |
| PUT | `/api/config/active-symbols` | 设置活跃币种池 |
| PUT | `/api/config/strategy-defaults` | 设置某个策略的默认参数 |
| PUT | `/api/config/backtest-defaults` | 设置回测默认值 |
| PUT | `/api/config/timeframes` | 设置可用 K线周期 |
| POST | `/api/config/reset` | 重置所有配置 |
| POST | `/api/backtest/single` | 单标的回测 |
| POST | `/api/backtest/scan` | 池子扫描 (返回 ranking + 组合曲线) |
| POST | `/api/backtest/filter` | 币种筛选 |
| GET | `/api/backtest/kline/{symbol}` | K线 + MA7/25/99 + 统计 |
| GET | `/api/data` | 列出所有缓存 |
| DELETE | `/api/data?timeframe=&symbol=` | 删除缓存 |

## 📊 内置策略

| ID | 名称 | 类型 | 参数 | 适合 |
|----|------|------|------|------|
| `ma_cross` | 双均线交叉 | trend | ma_short, ma_long | 趋势市 |
| `momentum_rotation` | 动量轮动 | momentum | top_n, hold, lookback | 牛市/震荡 |
| `rsi` | RSI 超买超卖 | mean_reversion | period, oversold, overbought | 震荡市 |
| `macd` | MACD 金叉死叉 | trend | fast, slow, signal | 中长线 |

## 🛠️ 技术栈

- **后端**: FastAPI + Uvicorn + Pydantic + PyYAML
- **前端**: Vue 3 + Vite + ECharts + Axios
- **数据**: Binance Spot API (无需 Key)
- **计算**: pandas + numpy + matplotlib
- **配置**: YAML + 自研单例加载器

## 📦 打包成 EXE

```bash
python build.py
# 产出: dist/K7Quant.exe (单文件，可发给任何人直接运行)
```

## ⚠️ 免责声明

本项目仅供**研究学习**，不构成任何投资建议。加密货币投资风险极高，过往表现不代表未来，请勿投入无法承受损失的资金。

## 📄 License

MIT