function toNumber(value) {
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

function roundNumber(value, digits = 12) {
  if (!Number.isFinite(value)) return 0
  const factor = 10 ** digits
  return Math.round((value + Number.EPSILON) * factor) / factor
}

function orderKeyFor(trade) {
  const orderId = trade?.orderId
  if (orderId !== undefined && orderId !== null && orderId !== '') return `order:${orderId}`
  const id = trade?.id || trade?.tradeId
  if (id !== undefined && id !== null && id !== '') return `trade:${id}`
  return `time:${trade?.time || trade?.created_at || Math.random()}`
}

export function normalizeExchangeTrade(trade) {
  const price = toNumber(trade?.price)
  const qty = toNumber(trade?.qty ?? trade?.executedQty ?? trade?.amount)
  const quoteQty = toNumber(trade?.quoteQty) || price * qty
  return {
    id: toNumber(trade?.id ?? trade?.tradeId),
    orderId: trade?.orderId ?? '',
    time: toNumber(trade?.time) || Date.parse(trade?.created_at || '') || 0,
    side: trade?.isBuyer === false ? 'sell' : 'buy',
    price,
    qty,
    quoteQty,
    commission: toNumber(trade?.commission),
    commissionAsset: trade?.commissionAsset || '',
    isMaker: !!trade?.isMaker,
  }
}

function formatCommission(commissionByAsset) {
  const parts = Object.entries(commissionByAsset)
    .filter(([, value]) => value > 0)
    .sort(([assetA], [assetB]) => assetA.localeCompare(assetB))
    .map(([asset, value]) => `${roundNumber(value, 12).toFixed(8)} ${asset || '-'}`)
  return parts.length ? parts.join(' + ') : '-'
}

function summarizeOrderGroup(key, fills) {
  const sortedFills = [...fills].sort((a, b) => b.time - a.time || b.id - a.id)
  const qty = roundNumber(sortedFills.reduce((sum, fill) => sum + fill.qty, 0))
  const quoteQty = roundNumber(sortedFills.reduce((sum, fill) => sum + fill.quoteQty, 0))
  const commissionByAsset = {}
  for (const fill of sortedFills) {
    if (!fill.commission) continue
    const asset = fill.commissionAsset || '-'
    commissionByAsset[asset] = roundNumber((commissionByAsset[asset] || 0) + fill.commission)
  }

  const makerValues = new Set(sortedFills.map((fill) => fill.isMaker))
  return {
    key,
    id: sortedFills[0]?.id || 0,
    orderId: sortedFills[0]?.orderId || '',
    time: Math.max(...sortedFills.map((fill) => fill.time)),
    side: sortedFills[0]?.side || 'buy',
    price: qty > 0 ? quoteQty / qty : 0,
    qty,
    quoteQty,
    commissionByAsset,
    commissionText: formatCommission(commissionByAsset),
    liquidity: makerValues.size > 1 ? 'Mixed' : (sortedFills[0]?.isMaker ? 'Maker' : 'Taker'),
    isMaker: makerValues.size === 1 ? !!sortedFills[0]?.isMaker : null,
    fillCount: sortedFills.length,
    fills: sortedFills,
  }
}

export function groupExchangeTradesByOrder(trades = []) {
  const groups = new Map()
  for (const rawTrade of trades || []) {
    const trade = normalizeExchangeTrade(rawTrade)
    if (trade.price <= 0 || trade.qty <= 0) continue
    const key = orderKeyFor(rawTrade)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(trade)
  }

  return [...groups.entries()]
    .map(([key, fills]) => summarizeOrderGroup(key, fills))
    .sort((a, b) => b.time - a.time || String(b.orderId).localeCompare(String(a.orderId)))
}
