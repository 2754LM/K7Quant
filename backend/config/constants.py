"""config/constants.py - 业务常量集中地
所有"不依赖用户配置"、纯业务约定的常量都在这里定义。

区别:
- config/settings.py: 用户可改的 YAML 配置 (port, commission, proxy, ...)
- config/constants.py: 硬编码业务常量 (Binance 白名单, 默认 symbol, ...)

注: BINANCE_TIMEFRAMES 必须在 fetcher 之前定义 (fetcher 复用)
"""
from typing import Set


# ============ Binance 业务常量 ============
# Binance 全集 timeframe (https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data)
# 1s 仅现货部分端点支持, 这里列出所有标准 interval
# 顺序按 Binance 官方文档: 秒 → 分 → 时 → 日 → 周 → 月
BINANCE_TIMEFRAMES = [
    "1s",
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d",
    "1w",
    "1M",
]
BINANCE_TIMEFRAMES_SET: Set[str] = set(BINANCE_TIMEFRAMES)


def is_valid_timeframe(tf: str) -> bool:
    """检查是否是 Binance 支持的 timeframe"""
    return tf in BINANCE_TIMEFRAMES_SET


# ============ 默认币种 (市值 top 25 USDT 交易对) ============
# 首次启动自动注册到 DB (services.symbol_service.init_default_symbols)
# 字段: (symbol, name_zh, name_en, category, market_cap_rank, description, tags)
DEFAULT_SYMBOLS = [
    # 主流币 (前 10)
    ("BTCUSDT", "比特币", "Bitcoin", "Layer 1", 1,
     "全球首个去中心化加密货币, 数字黄金, 抗审查的价值存储",
     ["主流", "价值存储", "PoW"]),
    ("ETHUSDT", "以太坊", "Ethereum", "Layer 1", 2,
     "智能合约平台, DeFi/NFT/DAO 生态基础, EVM 兼容",
     ["主流", "智能合约", "PoS"]),
    ("USDTUSDT", "泰达币", "Tether", "稳定币", 3,
     "锚定 1 美元, 交易量最大的稳定币",
     ["稳定币", "避险"]),
    ("BNBUSDT", "币安币", "BNB", "交易所", 4,
     "Binance 交易所平台币, BSC 链 gas, 定期销毁",
     ["平台币", "BSC", "交易所"]),
    ("SOLUSDT", "索拉纳", "Solana", "Layer 1", 5,
     "高性能公链, 65k TPS, 极低手续费, 适合高频 DeFi",
     ["高性能", "PoH", "NFT", "DeFi"]),
    ("USDCUSDT", "美元硬币", "USD Coin", "稳定币", 6,
     "受监管的美元稳定币, 透明度高",
     ["稳定币", "合规"]),
    ("XRPUSDT", "瑞波币", "Ripple", "支付", 7,
     "跨境支付网络, 银行合作广泛",
     ["支付", "跨境"]),
    ("DOGEUSDT", "狗狗币", "Dogecoin", "Meme", 8,
     "Meme 鼻祖, 马斯克效应",
     ["Meme", "支付", "PoW"]),
    ("ADAUSDT", "艾达币", "Cardano", "Layer 1", 9,
     "学术派公链, Ouroboros PoS, 学术研究驱动",
     ["学术", "PoS", "Layer 1"]),
    ("TRXUSDT", "波场", "TRON", "Layer 1", 10,
     "高吞吐量, USDT 流转量大, 适合稳定币转账",
     ["稳定币", "DApp"]),

    # Layer 1 / 公链
    ("AVAXUSDT", "雪崩", "Avalanche", "Layer 1", 11,
     "三链架构 (X/P/C), 子网定制, 高性能 EVM",
     ["子网", "EVM", "PoS"]),
    ("LINKUSDT", " Chainlink", "Chainlink", "预言机", 12,
     "去中心化预言机龙头, 喂价服务标准",
     ["预言机", "喂价", "DeFi"]),
    ("DOTUSDT", "波卡", "Polkadot", "Layer 0", 13,
     "跨链互操作, 平行链架构, Substrate 框架",
     ["跨链", "平行链"]),
    ("MATICUSDT", "Polygon", "Polygon", "Layer 2", 14,
     "以太坊侧链, 低 gas 兼容 EVM, zkEVM 路线",
     ["Layer 2", "EVM", "zk"]),
    ("NEARUSDT", "Near", "Near Protocol", "Layer 1", 15,
     "分片公链, 账户模型人性化, AI 集成",
     ["分片", "AI"]),

    # DeFi
    ("UNIUSDT", " Uniswap", "Uniswap", "DeFi", 16,
     "DEX 龙头, AMM 协议标准",
     ["DEX", "AMM", "DeFi"]),
    ("AAVEUSDT", " Aave", "Aave", "DeFi", 17,
     "去中心化借贷协议",
     ["借贷", "DeFi"]),
    ("CRVUSDT", " Curve", "Curve DAO", "DeFi", 18,
     "稳定币 DEX, 低滑点",
     ["稳定币", "DEX"]),

    # 其它
    ("LTCUSDT", "莱特币", "Litecoin", "支付", 19,
     "比特币分叉, 减半周期, 数字白银",
     ["老牌", "支付"]),
    ("BCHUSDT", "比特币现金", "Bitcoin Cash", "支付", 20,
     "比特币硬分叉, 大区块",
     ["分叉", "支付"]),
    ("ETCUSDT", "以太经典", "Ethereum Classic", "Layer 1", 21,
     "以太坊硬分叉, PoW 共识",
     ["分叉", "PoW"]),
    ("XLMUSDT", "恒星币", "Stellar", "支付", 22,
     "跨境支付, IBM 合作",
     ["支付", "跨境"]),
    ("FILUSDT", " Filecoin", "Filecoin", "存储", 23,
     "去中心化存储网络, IPFS 激励层",
     ["存储", "Web3"]),
    ("APTUSDT", " Aptos", "Aptos", "Layer 1", 24,
     "Move 语言公链, Diem 团队, 并行执行",
     ["Move", "并行"]),
    ("ARBUSDT", " Arbitrum", "Arbitrum", "Layer 2", 25,
     "以太坊 Optimistic Rollup 龙头",
     ["Layer 2", "Optimistic"]),
]


# ============ 因子 / 策略 内置列表注册 ============
# 这些在 services/ 里 init_xxx() 启动时使用
BUILTIN_STRATEGY_CATEGORY = "trend"   # 默认分类
BUILTIN_FACTOR_CATEGORY = "统计类"


# ============ 回测默认值 (可被 config.yaml 覆盖) ============
DEFAULT_BACKTEST_START_DATE = "20240101"
DEFAULT_BACKTEST_TIMEFRAME = "4h"
DEFAULT_BACKTEST_CAPITAL = 10000.0
DEFAULT_COMMISSION_RATE = 0.0004
DEFAULT_SLIPPAGE = 0.0005


# ============ 限流 / 安全 ============
API_LOG_TAIL_DEFAULT_LINES = 50
API_LOG_TAIL_MAX_LINES = 500
API_BACKTEST_TIMEOUT_SECONDS = 300

# 实盘 (live trader)
LIVE_TF_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800,
}
LIVE_DEFAULT_TIMEFRAME = "1m"
LIVE_LOOKBACK_BARS = 320
LIVE_SLTP_TICK_SECONDS = 20