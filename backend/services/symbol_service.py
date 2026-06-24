"""币种初始化 (启动时调用)"""
from backend.repositories.crud import crud


# 25 个主流币种 (与 symbols.yaml 同步)
DEFAULT_SYMBOLS = [
    ("BTCUSDT", "比特币", "Bitcoin", "layer1", 1, "中本聪于 2009 年创立, 总量 2100 万", ["市值第一", "抗审查", "PoW"]),
    ("ETHUSDT", "以太坊", "Ethereum", "layer1", 2, "智能合约平台, DeFi/NFT 生态最大", ["智能合约", "DeFi", "PoS"]),
    ("BNBUSDT", "币安币", "BNB", "exchange", 4, "Binance 平台币", ["平台币", "BNB Chain"]),
    ("SOLUSDT", "索拉纳", "Solana", "layer1", 5, "高性能公链, TPS 6.5 万", ["高性能", "meme"]),
    ("XRPUSDT", "瑞波币", "XRP", "payment", 6, "跨境支付", ["支付", "跨境结算"]),
    ("ADAUSDT", "艾达币", "Cardano", "layer1", 8, "学术派公链", ["学术派", "PoS"]),
    ("DOGEUSDT", "狗狗币", "Dogecoin", "meme", 9, "2013 玩笑币, meme 王", ["meme", "社区"]),
    ("AVAXUSDT", "雪崩", "Avalanche", "layer1", 10, "亚秒级 L1", ["L1", "快"]),
    ("MATICUSDT", "多边形", "Polygon", "layer2", 11, "以太坊 L2 聚合器", ["L2", "Polygon"]),
    ("DOTUSDT", "波卡", "Polkadot", "layer0", 12, "跨链协议", ["跨链"]),
    ("LINKUSDT", "链接币", "Chainlink", "oracle", 14, "去中心化预言机龙头", ["预言机", "DeFi"]),
    ("TRXUSDT", "波场币", "TRON", "layer1", 15, "USDT 主要网络", ["USDT"]),
    ("LTCUSDT", "莱特币", "Litecoin", "payment", 18, "比特币分叉", ["老牌"]),
    ("ATOMUSDT", "宇宙", "Cosmos", "layer0", 20, "区块链互联网 IBC", ["跨链", "IBC"]),
    ("NEARUSDT", "接近协议", "NEAR", "layer1", 22, "分片公链", ["分片", "AI"]),
    ("UNIUSDT", "Uniswap", "Uniswap", "defi", 25, "DEX 龙头 AMM", ["DEX", "AMM"]),
    ("APTUSDT", "艾普科", "Aptos", "layer1", 28, "Meta Diem 遗产", ["L1", "Move"]),
    ("ARBUSDT", "奥术", "Arbitrum", "layer2", 30, "以太坊最大 L2", ["L2", "Optimistic"]),
    ("OPUSDT", "乐观", "Optimism", "layer2", 32, "Optimistic L2", ["L2"]),
    ("SUIUSDT", "水", "Sui", "layer1", 34, "Move 语言高性能 L1", ["L1", "Move"]),
    ("INJUSDT", "注射器", "Injective", "defi", 38, "Cosmos 衍生品", ["衍生品"]),
    ("TIAUSDT", "钛", "Celestia", "modular", 40, "模块化 DA 层", ["模块化", "DA"]),
    ("SEIUSDT", "Sei", "Sei", "layer1", 45, "交易专用 L1", ["L1", "交易"]),
    ("RNDRUSDT", "渲染币", "Render", "ai", 50, "去中心化 GPU 渲染", ["AI", "GPU"]),
    ("FETUSDT", "Fetch.ai", "Fetch.ai", "ai", 55, "AI 代理项目", ["AI", "Agent"]),
]

DEFAULT_ACTIVE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT"]


def init_default_symbols():
    """启动时把默认币种写库 + 设置活跃池"""
    existing = {s["symbol"] for s in crud.list_symbols()}
    active = {s["symbol"] for s in crud.list_symbols(active_only=True)}

    for sym, name_zh, name_en, cat, rank, desc, tags in DEFAULT_SYMBOLS:
        if sym not in existing:
            crud.upsert_symbol(
                symbol=sym, name_zh=name_zh, name_en=name_en,
                category=cat, market_cap_rank=rank,
                description=desc, tags=tags, is_active=0,
            )

    # 第一次启动激活默认池
    if not active:
        crud.set_active_symbols(DEFAULT_ACTIVE)
        active = set(DEFAULT_ACTIVE)

    # 同步 active_symbols 配置
    from backend.config import config as sys_config
    cur = sys_config.load_config()
    if not cur.get("active_symbols"):
        cur["active_symbols"] = sorted(active)
        sys_config.save_config(cur)