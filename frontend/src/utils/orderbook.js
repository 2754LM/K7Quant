// 订单簿 / 最近成交: 从 K 线数据合成
// 注: 这是基于历史数据的「推测」订单簿, 不是真实实时深度
// 但对于回测研究, 能看到价格分布密度和最近成交方向

// 从最近 N 根 K 线合成「最近成交」(trades)
// 每根 K 线视为一次「成交聚合」: 价格取 close, 数量取 volume, 方向看 close vs open
export function synthRecentTrades(kline, n = 30) {
  if (!kline?.length) return []
  const last = kline.slice(-n).reverse()  // 最新的在前
  return last.map(k => {
    const chg = k.close - k.open
    return {
      time: k.date,
      price: k.close,
      amount: k.volume || 0,
      side: chg >= 0 ? 'buy' : 'sell',
      // 模拟一单拆 3-8 笔, 但这里只显示聚合后 1 笔
    }
  })
}

// 从最近 N 根 K 线合成订单簿 (围绕当前价 ±1.5%)
// 用 close 价 + 该 K 线的 (high-low) 范围当深度近似
export function synthOrderBook(kline, lastPrice, levels = 8) {
  if (!kline?.length || lastPrice == null) return { bids: [], asks: [] }
  const recent = kline.slice(-Math.max(20, levels * 3))
  // tick size ≈ 0.05% * price, 上下各 levels 档
  const tickPct = 0.0005
  const tickSize = Math.max(lastPrice * tickPct, getTickSize(lastPrice))
  const bids = []
  const asks = []
  for (let i = 1; i <= levels; i++) {
    const bidPrice = lastPrice - i * tickSize
    const askPrice = lastPrice + i * tickSize
    // 深度 = 该价位 ±tick 范围内 close 落入的次数 × 成交量
    const bidDepth = countClosesNear(recent, bidPrice, tickSize) * 100
    const askDepth = countClosesNear(recent, askPrice, tickSize) * 100
    bids.push({
      price: bidPrice,
      amount: Math.max(50, bidDepth + Math.random() * 80),  // 加点随机让 UI 不死板
      total: 0,
    })
    asks.push({
      price: askPrice,
      amount: Math.max(50, askDepth + Math.random() * 80),
      total: 0,
    })
  }
  // 计算累计 (asks 从上往下累计, bids 从上往下累计)
  asks.reverse()
  let askAcc = 0
  for (const a of asks) { askAcc += a.amount; a.total = askAcc }
  let bidAcc = 0
  for (const b of bids) { bidAcc += b.amount; b.total = bidAcc }
  return { bids, asks: asks.reverse() }  // asks 重新正序
}

function countClosesNear(klines, price, range) {
  let count = 0
  for (const k of klines) {
    if (Math.abs(k.close - price) <= range) count++
  }
  return count
}

function getTickSize(price) {
  // 根据价格量级给个合理 tick (跟 Binance 类似)
  if (price >= 1000) return 0.1
  if (price >= 100) return 0.01
  if (price >= 1) return 0.001
  if (price >= 0.01) return 0.0001
  return 0.00001
}

// 把收盘价序列归一化成「百分比变化」, 用于多币种对比
export function normalizeToPercent(kline) {
  if (!kline?.length) return []
  const base = kline[0].close
  return kline.map(k => ({
    date: k.date,
    value: base ? ((k.close - base) / base) * 100 : 0,
  }))
}
