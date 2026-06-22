const STABLE_ASSETS = new Set(['USDT', 'USDC', 'BUSD', 'FDUSD', 'TUSD', 'USDP', 'DAI'])

function num(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function round(value, digits = 10) {
  return Number(num(value).toFixed(digits))
}

function normalizeAsset(asset) {
  return String(asset || '').toUpperCase()
}

function normalizeSymbol(symbol) {
  return String(symbol || '').toUpperCase()
}

function parseSymbolAssets(symbol) {
  const normalized = normalizeSymbol(symbol)
  const quoteAssets = ['USDT', 'USDC', 'BUSD', 'FDUSD', 'TUSD', 'USDP', 'DAI']
  const quoteAsset = quoteAssets.find((asset) => normalized.endsWith(asset)) || 'USDT'
  return {
    baseAsset: normalized.endsWith(quoteAsset) ? normalized.slice(0, -quoteAsset.length) : normalized,
    quoteAsset,
  }
}

function addHolding(holdings, asset, delta) {
  const name = normalizeAsset(asset)
  const amount = num(delta)
  if (!name || Math.abs(amount) < 1e-12) return
  holdings.set(name, round(num(holdings.get(name)) + amount, 12))
}

function holdingsFromBalances(balances = []) {
  const holdings = new Map()
  for (const balance of balances) {
    const asset = normalizeAsset(balance?.asset)
    const free = num(balance?.free)
    const locked = num(balance?.locked)
    const total = num(balance?.total ?? free + locked)
    if (asset && Math.abs(total) > 1e-12) holdings.set(asset, round(total, 12))
  }
  return holdings
}

function normalizeTrade(trade, fallbackSymbol = '') {
  const price = num(trade?.price)
  const qty = num(trade?.qty ?? trade?.executedQty ?? trade?.amount)
  return {
    id: Number(trade?.id ?? trade?.tradeId ?? 0),
    symbol: normalizeSymbol(trade?.symbol || fallbackSymbol),
    time: Number(trade?.time) || Date.parse(trade?.created_at || '') || 0,
    isBuyer: trade?.isBuyer === false ? false : String(trade?.side || '').toLowerCase() !== 'sell',
    price,
    qty,
    quoteQty: num(trade?.quoteQty) || price * qty,
    commission: num(trade?.commission),
    commissionAsset: normalizeAsset(trade?.commissionAsset),
  }
}

function applyTrade(holdings, trade, direction = 1) {
  const { baseAsset, quoteAsset } = parseSymbolAssets(trade.symbol)
  if (!baseAsset || !quoteAsset) return
  const side = trade.isBuyer ? 1 : -1
  addHolding(holdings, baseAsset, direction * side * trade.qty)
  addHolding(holdings, quoteAsset, direction * -side * trade.quoteQty)
  addHolding(holdings, trade.commissionAsset, direction * -trade.commission)
}

function tradePriceMap(trade, prices = {}) {
  const { baseAsset, quoteAsset } = parseSymbolAssets(trade.symbol)
  if (!baseAsset || !quoteAsset || trade.price <= 0) return {}

  const quotePrice = STABLE_ASSETS.has(quoteAsset) ? 1 : priceForAsset(quoteAsset, prices)
  const basePrice = quotePrice > 0 ? trade.price * quotePrice : trade.price
  return { [`${baseAsset}USDT`]: basePrice }
}

function valueHoldings(holdings, { selectedAsset, prices, time }) {
  let totalValue = 0
  let selectedValue = 0
  const selectedQty = num(holdings.get(selectedAsset))

  for (const [asset, qty] of holdings.entries()) {
    if (Math.abs(qty) < 1e-12) continue
    const price = priceForAsset(asset, prices)
    if (price <= 0) continue
    const value = qty * price
    totalValue += value
    if (asset === selectedAsset) selectedValue = value
  }

  return {
    time: Number(time),
    totalValue: round(totalValue),
    selectedValue: round(selectedValue),
    selectedQty: round(selectedQty),
  }
}

export function priceForAsset(asset, prices = {}) {
  const name = normalizeAsset(asset)
  if (!name) return 0
  if (STABLE_ASSETS.has(name)) return 1
  return num(prices[`${name}USDT`] ?? prices[name])
}

export function buildAccountValuation(balances = [], prices = {}, { symbol = '' } = {}) {
  const selectedSymbol = normalizeSymbol(symbol)
  const baseAsset = selectedSymbol.endsWith('USDT') ? selectedSymbol.slice(0, -4) : selectedSymbol
  const assetRows = []
  const unpricedAssets = []
  let totalValue = 0

  for (const balance of balances) {
    const asset = normalizeAsset(balance?.asset)
    const free = num(balance?.free)
    const locked = num(balance?.locked)
    const total = num(balance?.total ?? free + locked)
    if (!asset || total <= 0) continue

    const price = priceForAsset(asset, prices)
    const value = price > 0 ? total * price : 0
    if (price > 0) totalValue += value
    else unpricedAssets.push(asset)

    assetRows.push({
      asset,
      free: round(free),
      locked: round(locked),
      total: round(total),
      price: round(price),
      value: round(value),
      priced: price > 0,
    })
  }

  for (const row of assetRows) {
    row.allocation = totalValue > 0 && row.value > 0 ? round(row.value / totalValue, 6) : 0
  }

  assetRows.sort((a, b) => b.value - a.value || b.total - a.total || a.asset.localeCompare(b.asset))

  const baseBalance = assetRows.find((row) => row.asset === baseAsset)
  const selectedPrice = priceForAsset(baseAsset, prices)
  const selectedQty = baseBalance?.total || 0
  const selectedFree = baseBalance?.free || 0
  const selectedLocked = baseBalance?.locked || 0
  const selectedValue = selectedPrice > 0 ? selectedQty * selectedPrice : 0

  return {
    symbol: selectedSymbol,
    totalValue: round(totalValue),
    assetRows,
    unpricedAssets,
    selectedAsset: baseAsset,
    selectedQty: round(selectedQty),
    selectedFree: round(selectedFree),
    selectedLocked: round(selectedLocked),
    selectedPrice: round(selectedPrice),
    selectedValue: round(selectedValue),
    pricedAssetCount: assetRows.filter((row) => row.priced).length,
    assetCount: assetRows.length,
  }
}

export function appendAccountSnapshot(
  history = [],
  valuation,
  timestamp = Date.now(),
  { maxLength = 240, force = false } = {}
) {
  const totalValue = num(valuation?.totalValue)
  if (totalValue <= 0) return history.slice(-maxLength)

  const last = history[history.length - 1]
  if (!force && last && Math.abs(num(last.totalValue) - totalValue) < 1e-8) {
    return history.slice(-maxLength)
  }

  return [
    ...history,
    {
      time: Number(timestamp),
      totalValue: round(totalValue),
      selectedValue: round(valuation?.selectedValue),
      selectedQty: round(valuation?.selectedQty),
    },
  ].slice(-maxLength)
}

export function buildAccountPerformance(history = []) {
  const points = (history || [])
    .map((point) => ({ time: Number(point?.time) || 0, totalValue: num(point?.totalValue) }))
    .filter((point) => point.time > 0 && point.totalValue > 0)
    .sort((a, b) => a.time - b.time)

  if (points.length < 2) {
    return {
      startValue: 0,
      endValue: 0,
      profitAmount: 0,
      profitRate: 0,
      tradeCount: 0,
      winCount: 0,
      lossCount: 0,
      winRate: 0,
      payoffRatio: 0,
      expectancy: 0,
      avgWin: 0,
      avgLoss: 0,
    }
  }

  const changes = []
  for (let i = 1; i < points.length; i += 1) {
    const delta = round(points[i].totalValue - points[i - 1].totalValue)
    if (Math.abs(delta) > 1e-8) changes.push(delta)
  }

  const wins = changes.filter((delta) => delta > 0)
  const losses = changes.filter((delta) => delta < 0)
  const sumWins = wins.reduce((sum, value) => sum + value, 0)
  const sumLosses = losses.reduce((sum, value) => sum + value, 0)
  const avgWin = wins.length ? sumWins / wins.length : 0
  const avgLoss = losses.length ? sumLosses / losses.length : 0
  const tradeCount = changes.length
  const startValue = points[0].totalValue
  const endValue = points[points.length - 1].totalValue
  const profitAmount = endValue - startValue

  return {
    startValue: round(startValue),
    endValue: round(endValue),
    profitAmount: round(profitAmount),
    profitRate: startValue > 0 ? round(profitAmount / startValue, 8) : 0,
    tradeCount,
    winCount: wins.length,
    lossCount: losses.length,
    winRate: tradeCount ? wins.length / tradeCount : 0,
    payoffRatio: avgWin > 0 && avgLoss < 0 ? avgWin / Math.abs(avgLoss) : 0,
    expectancy: tradeCount ? round(changes.reduce((sum, value) => sum + value, 0) / tradeCount) : 0,
    avgWin: round(avgWin),
    avgLoss: round(avgLoss),
  }
}

export function assetsNeedingUsdtTicker(balances = [], knownSymbols = []) {
  const available = new Set(knownSymbols.map((s) => normalizeSymbol(s)))
  const assets = new Set()

  for (const balance of balances) {
    const asset = normalizeAsset(balance?.asset)
    const free = num(balance?.free)
    const locked = num(balance?.locked)
    const total = num(balance?.total ?? free + locked)
    if (!asset || total <= 0 || STABLE_ASSETS.has(asset)) continue
    const symbol = `${asset}USDT`
    if (!available.size || available.has(symbol)) assets.add(asset)
  }

  return [...assets].sort()
}

export function buildAccountHistoryFromTrades(
  balances = [],
  trades = [],
  { symbol = '', prices = {}, now = Date.now(), maxLength = 240 } = {}
) {
  const { baseAsset: selectedAsset } = parseSymbolAssets(symbol)
  if (!selectedAsset) return []

  const normalizedTrades = trades
    .map((trade) => normalizeTrade(trade, symbol))
    .filter((trade) => trade.symbol && trade.time > 0 && trade.price > 0 && trade.qty > 0)
    .sort((a, b) => a.time - b.time || a.id - b.id)

  if (!normalizedTrades.length) return []

  const holdings = holdingsFromBalances(balances)

  for (const trade of [...normalizedTrades].reverse()) {
    applyTrade(holdings, trade, -1)
  }

  const history = []
  let historicalPrices = { ...prices }
  for (const trade of normalizedTrades) {
    applyTrade(holdings, trade, 1)
    historicalPrices = { ...historicalPrices, ...tradePriceMap(trade, historicalPrices) }
    history.push(valueHoldings(holdings, {
      selectedAsset,
      prices: historicalPrices,
      time: trade.time,
    }))
  }

  const last = history[history.length - 1]
  if (Number(now) > num(last?.time)) {
    history.push(valueHoldings(holdings, {
      selectedAsset,
      prices,
      time: Number(now),
    }))
  }

  return history
    .filter((point) => point.time > 0 && point.totalValue > 0)
    .slice(-maxLength)
}
