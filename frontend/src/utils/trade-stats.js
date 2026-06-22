const EPS = 1e-12

function num(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function round(value, digits = 10) {
  const n = num(value)
  return Number(n.toFixed(digits))
}

function tradeTime(trade) {
  const t = Date.parse(trade?.created_at || '')
  return Number.isFinite(t) ? t : 0
}

function normalizeTrade(trade) {
  return {
    ...trade,
    id: trade?.id ?? 0,
    symbol: String(trade?.symbol || '').toUpperCase(),
    side: String(trade?.side || '').toLowerCase(),
    price: num(trade?.price),
    amount: num(trade?.amount),
    created_at: trade?.created_at || '',
    _time: tradeTime(trade),
  }
}

export function buildTradeAnalytics(trades = [], { symbol, currentPrice = 0 } = {}) {
  const selectedSymbol = String(symbol || '').toUpperCase()
  const priceNow = num(currentPrice)
  const filtered = trades
    .map(normalizeTrade)
    .filter((trade) => !selectedSymbol || trade.symbol === selectedSymbol)
    .filter((trade) => trade.price > 0 && trade.amount > 0 && ['buy', 'sell'].includes(trade.side))
    .sort((a, b) => a._time - b._time || a.id - b.id)

  const lots = []
  const rows = []
  const markers = []
  let costBasis = 0
  let positionQty = 0
  let realizedPnl = 0
  let totalBuyCost = 0
  let buyCount = 0
  let sellCount = 0
  let closedTradeCount = 0
  let winningSellCount = 0

  for (const trade of filtered) {
    const notional = trade.price * trade.amount
    let rowRealized = 0
    let matchedQty = 0
    let unmatchedQty = 0

    if (trade.side === 'buy') {
      buyCount += 1
      totalBuyCost += notional
      positionQty += trade.amount
      costBasis += notional
      lots.push({ qty: trade.amount, price: trade.price })
    } else {
      sellCount += 1
      let remaining = trade.amount
      let matchedCost = 0

      while (remaining > EPS && lots.length) {
        const lot = lots[0]
        const used = Math.min(lot.qty, remaining)
        matchedQty += used
        matchedCost += used * lot.price
        lot.qty -= used
        remaining -= used
        if (lot.qty <= EPS) lots.shift()
      }

      unmatchedQty = remaining > EPS ? remaining : 0
      rowRealized = matchedQty * trade.price - matchedCost
      realizedPnl += rowRealized
      positionQty = Math.max(0, positionQty - matchedQty)
      costBasis = Math.max(0, costBasis - matchedCost)

      if (matchedQty > EPS) {
        closedTradeCount += 1
        if (rowRealized > 0) winningSellCount += 1
      }
    }

    const avgCost = positionQty > EPS ? costBasis / positionQty : 0
    const row = {
      ...trade,
      notional: round(notional),
      realizedPnl: round(rowRealized),
      matchedQty: round(matchedQty),
      unmatchedQty: round(unmatchedQty),
      positionQty: round(positionQty),
      avgCost: round(avgCost),
    }
    rows.push(row)
    markers.push({
      id: trade.id,
      symbol: trade.symbol,
      side: trade.side,
      price: trade.price,
      amount: trade.amount,
      notional: round(notional),
      created_at: trade.created_at,
      realizedPnl: row.realizedPnl,
    })
  }

  const avgCost = positionQty > EPS ? costBasis / positionQty : 0
  const marketValue = priceNow > 0 ? positionQty * priceNow : 0
  const unrealizedPnl = priceNow > 0 ? positionQty * (priceNow - avgCost) : 0
  const totalPnl = realizedPnl + unrealizedPnl
  const totalReturnPct = totalBuyCost > EPS ? totalPnl / totalBuyCost : 0

  return {
    symbol: selectedSymbol,
    currentPrice: round(priceNow),
    tradeCount: filtered.length,
    buyCount,
    sellCount,
    positionQty: round(positionQty),
    costBasis: round(costBasis),
    avgCost: round(avgCost),
    marketValue: round(marketValue),
    realizedPnl: round(realizedPnl),
    unrealizedPnl: round(unrealizedPnl),
    totalPnl: round(totalPnl),
    totalBuyCost: round(totalBuyCost),
    totalReturnPct: round(totalReturnPct),
    closedTradeCount,
    winRate: closedTradeCount ? round(winningSellCount / closedTradeCount) : 0,
    rows,
    rowsDesc: [...rows].reverse(),
    markers,
    markersDesc: [...markers].reverse(),
  }
}
