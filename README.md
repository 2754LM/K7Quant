# K7Quant - 币安加密货币量化回测系统

完整的前后端加密货币量化回测平台，基于 Binance 公开 API，支持 4 种经典策略和多周期回测。

## 功能

- 📊 **4 种内置策略**：双均线交叉、动量轮动、RSI 超买超卖、MACD 金叉死叉
- ⏱️ **12 种 K 线周期**：1m / 5m / 15m / 1h / 4h / 1d / 1w 等
- 💰 **25 个 USDT 交易对**：BTC、ETH、BNB、SOL 及主流山寨币
- 🎯 **一键扫描**：自动跑完全部币种，按夏普排序
- 📈 **专业图表**：净值曲线（vs BTC 基准）、K线图 + MA7/25/99 叠加
- 🔍 **多条件筛选**：按涨幅/价格/夏普筛选
- 📚 **新手友好**：白话教学 + 6 步量化工作流

## 启动

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt

# 2. 构建前端
cd frontend
npm install --registry https://registry.npmmirror.com
npm run build
cd ..

# 3. 启动（自动打开浏览器）
python run.py
```

访问 http://127.0.0.1:8765

## 项目结构

```
.
├── quant_core/          # 核心代码
│   ├── config.py        # 配置 (币种池/周期)
│   ├── data/fetcher.py  # Binance API
│   └── backtest.py      # 回测引擎 + 4 个策略
├── backend/             # FastAPI 后端
├── frontend/            # Vue3 + Vite + ECharts 前端
├── run.py               # 一键启动
├── install.bat          # Windows 一键安装
├── start.bat            # Windows 一键启动
└── build.py             # PyInstaller 打包
```

## 内置策略

| 策略 | 参数 | 适合 |
|------|------|------|
| 双均线 MA 交叉 | ma_short, ma_long | 趋势市 |
| 动量轮动 | top_n, hold, lookback | 牛市 |
| RSI 超买超卖 | period, oversold, overbought | 震荡市 |
| MACD 金叉死叉 | fast, slow, signal | 中长线 |

## 数据来源

[Binance Spot API](https://binance-docs.github.io/apidocs/spot/en/) — 公开行情，无需 API Key

## 打包成 EXE

```bash
python build.py
# 产出: dist/K7Quant.exe
```

## License

MIT