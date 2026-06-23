<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { KLineChartPro } from '@klinecharts/pro'
import '@klinecharts/pro/dist/klinecharts-pro.css'
import * as echarts from 'echarts'
import { BinanceDatafeed } from '../utils/klinechart-datafeed'
import {
  getTradeConnectivity, getTradeStatus, getTradeAccount,
  getOpenOrders, placeOrder, cancelOrder, listTrades, listSymbols, getExchangeInfo, getMyTrades,
  resetSandbox, getStrategies, getLiveStatus, startLive, stopLive,
} from '../api'
import { subscribeTicker } from '../utils/binance-ws'
import { buildTradeAnalytics } from '../utils/trade-stats'
import {
  appendAccountSnapshot,
  assetsNeedingUsdtTicker,
  buildAccountPerformance,
  buildAccountHistoryFromTrades,
  buildAccountValuation,
} from '../utils/account-valuation'
import { groupExchangeTradesByOrder } from '../utils/exchange-trades'
import { formatClock } from '../utils/time-label'
import { syncAccountEquityIndicator } from '../utils/account-equity-indicator'
import { syncTradeOverlays } from '../utils/trade-overlays'
import StateView from '../components/StateView.vue'
import { useTimeframes } from '../composables/useTimeframes'

// ---- 状态 ----
const conn = ref({})
const status = ref({})
const balances = ref([])
const openOrders = ref([])
const localTrades = ref([])
const exchangeTrades = ref([])
const accountExchangeTrades = ref([])
const accountExchangeTradeSymbols = ref([])
const symbols = ref([])

const loading = ref(false)
const error = ref('')
const tradesError = ref('')
const exchangeTradesError = ref('')
const accountExchangeTradesError = ref('')
const accountExchangeTradesLoading = ref(false)
const accountExchangeTradesLoaded = ref(false)
const submitting = ref(false)
const toasts = ref([])   // 左下角气泡通知
const lastWsUpdateAt = ref(null)
const lastDataRefreshAt = ref(null)
const ACCOUNT_HISTORY_KEY = 'k7quant:trade-account-value-history'
const RESET_EPOCH_KEY = 'k7quant:trade-reset-epoch'
const STABLE_ASSETS = new Set(['USDT', 'USDC', 'BUSD', 'FDUSD', 'TUSD', 'USDP', 'DAI'])
const DUST_USDT = 5            // 预览里低于该市值的持仓视作可能卖不掉的 dust (后端按 minNotional 最终判定)
const expandedOrderIds = ref(new Set())
let toastSeq = 0

// ---- 沙盒重置 ----
const resetEpoch = ref(loadResetEpoch())   // 重置时间点(ms): 过滤此前的币安成交, 让曲线/收益归零
const showResetModal = ref(false)
const resetting = ref(false)
const resetReport = ref(null)              // 执行后战报; null 时弹窗显示确认预览

// ---- 策略实盘 ----
const strategies = ref([])
const live = ref({ running: false, logs: [] })
const liveForm = reactive({ strategyId: null, symbol: 'BTCUSDT', timeframe: '1h' })
const { list: liveTimeframes } = useTimeframes()  // 从后端 Binance 白名单拉
const showLiveConfirm = ref(false)
const liveStarting = ref(false)
const liveStopping = ref(false)
const selectedStrategyName = computed(() =>
  strategies.value.find((s) => s.id === liveForm.strategyId)?.name || '—')

const form = reactive({
  symbol: 'BTCUSDT', side: 'BUY', type: 'LIMIT',
  quantity: 0.001, price: null, time_in_force: 'GTC',
})

const connected = computed(() => conn.value?.credentials_valid)
const configured = computed(() => conn.value?.configured)
const balanceTickerPrices = ref({})
const accountHistory = ref(loadAccountHistory())
const tradeAnalytics = computed(() => buildTradeAnalytics(localTrades.value, {
  symbol: form.symbol,
  currentPrice: lastPrice.value,
}))
const priceMap = computed(() => {
  const map = { ...balanceTickerPrices.value }
  if (form.symbol && lastPrice.value > 0) map[form.symbol] = lastPrice.value
  return map
})
const accountValuation = computed(() => buildAccountValuation(balances.value, priceMap.value, {
  symbol: form.symbol,
}))
const positionRows = computed(() => accountValuation.value.assetRows || [])
// 过滤掉重置时间点之前的币安成交 (币安服务器侧记录删不掉, 只能按 epoch 隐藏, 让曲线/收益从重置后重算)
function afterReset(trades) {
  const epoch = resetEpoch.value
  if (!epoch) return trades
  return trades.filter((t) => Number(t?.time) >= epoch)
}
const tradeDerivedAccountHistory = computed(() => buildAccountHistoryFromTrades(
  balances.value,
  afterReset(accountExchangeTrades.value),
  {
    symbol: form.symbol,
    prices: priceMap.value,
    now: lastWsUpdateAt.value ? new Date(lastWsUpdateAt.value).getTime() : Date.now(),
  }
))
// 收益指标用: 成交级别 (稀疏), 避免把每个价格 tick 当成一笔交易
const accountHistoryForChart = computed(() => (
  tradeDerivedAccountHistory.value.length ? tradeDerivedAccountHistory.value : accountHistory.value
))
const accountPerformance = computed(() => buildAccountPerformance(accountHistoryForChart.value))
// 图表用: 把"成交重建"(稀疏结构点) 与"本地快照"(随行情 tick 密集记录) 按时间合并去重,
// 否则只有 2 个点会被前向填充成一条直线, 看不出资产随价格的波动。
const accountEquityCurve = computed(() => {
  const derived = tradeDerivedAccountHistory.value
  const snaps = accountHistory.value
  if (!derived.length) return snaps
  if (!snaps.length) return derived
  const seen = new Set()
  const merged = []
  for (const p of [...derived, ...snaps].sort((a, b) => Number(a.time) - Number(b.time))) {
    const t = Number(p?.time)
    const v = Number(p?.totalValue)
    if (!(t > 0 && v > 0) || seen.has(t)) continue
    seen.add(t)
    merged.push(p)
  }
  return merged.slice(-480)
})
const accountHistorySource = computed(() => (
  tradeDerivedAccountHistory.value.length ? '从全账户成交重建' : '从打开页面记录'
))
const accountHistoryCoverage = computed(() => {
  const parts = [`${accountEquityCurve.value.length} 点`]
  if (accountExchangeTradeSymbols.value.length) parts.push(`${accountExchangeTradeSymbols.value.length} 币对`)
  if (accountExchangeTradesLoading.value) parts.push('扫描中')
  return parts.join(' · ')
})
const tradeMarkers = computed(() => tradeAnalytics.value.markersDesc.slice(0, 10))
const chartTradeMarkers = computed(() => tradeAnalytics.value.markers)
const exchangeOrderRows = computed(() => groupExchangeTradesByOrder(afterReset(exchangeTrades.value)))
const exchangeFillCount = computed(() => exchangeOrderRows.value.reduce((sum, order) => sum + order.fillCount, 0))
const currentSymbolTrades = computed(() => tradeAnalytics.value.rowsDesc)

// 可用余额 / 成本估算 (让 -2010 余额不足一目了然)
const baseAsset = computed(() => form.symbol.replace('USDT', ''))
function freeOf(asset) {
  const b = balances.value.find((x) => x.asset === asset)
  return b ? Number(b.free) : 0
}
// 买入看 USDT, 卖出看 base 币
const availAsset = computed(() => (form.side === 'BUY' ? 'USDT' : baseAsset.value))
const availFree = computed(() => freeOf(availAsset.value))
const estCost = computed(() => {
  const q = Number(form.quantity) || 0
  const p = Number(form.price) || 0
  return form.type === 'LIMIT' ? q * p : 0
})
function fillMax() {
  if (form.side === 'SELL') form.quantity = freeOf(baseAsset.value)
}

// ---- 实时市价 + 下单精度 ----
const lastPrice = ref(0)       // 来自 Binance WS ticker 流的最新成交价
const stepSize = ref(0.00001)  // LOT_SIZE 数量步进
const tickSize = ref(0.01)     // PRICE_FILTER 价格步进
const pct = ref(0)             // 比例滑块 0~100
let priceUnsub = null
const balancePriceUnsubs = new Map()

function decimalsOf(step) {
  const s = String(step)
  if (s.includes('e') || s.includes('E')) return Math.max(0, -Math.floor(Math.log10(Number(step))))
  return s.includes('.') ? s.split('.')[1].replace(/0+$/, '').length : 0
}
function floorToStep(value, step) {
  const st = Number(step) || 0
  if (st <= 0) return value
  const n = Math.floor((value + 1e-12) / st) * st
  return Number(n.toFixed(decimalsOf(step)))
}

// 订阅当前币种实时价格 (ticker 最新成交价)
function watchPrice(ticker) {
  if (priceUnsub) { priceUnsub(); priceUnsub = null }
  lastPrice.value = 0
  lastWsUpdateAt.value = null
  priceUnsub = subscribeTicker(ticker, (quote) => {
    lastPrice.value = quote.price
    lastWsUpdateAt.value = new Date()
  })
}

// 拉该币种的下单精度 (避免 -1013 精度错误)
async function loadSymbolFilters(ticker) {
  try {
    const r = await getExchangeInfo(ticker)
    const f = r.data?.filters || {}
    stepSize.value = Number(f.LOT_SIZE?.stepSize) || stepSize.value
    tickSize.value = Number(f.PRICE_FILTER?.tickSize) || tickSize.value
  } catch {}
}

// 取当前市价填入限价
function useMarketPrice() {
  if (lastPrice.value > 0) form.price = floorToStep(lastPrice.value, tickSize.value)
}

// 按持仓/资金比例计算下单数量
function applyPct(p) {
  pct.value = p
  const refPrice = form.type === 'LIMIT' ? (Number(form.price) || lastPrice.value) : lastPrice.value
  if (form.side === 'BUY') {
    if (!refPrice) return flash('error', '等待行情价格, 稍候再试 (或先填限价)')
    const budget = freeOf('USDT') * (p / 100)
    form.quantity = floorToStep(budget / refPrice, stepSize.value)
  } else {
    form.quantity = floorToStep(freeOf(baseAsset.value) * (p / 100), stepSize.value)
  }
}

function loadAccountHistory() {
  try {
    const raw = localStorage.getItem(ACCOUNT_HISTORY_KEY)
    const parsed = JSON.parse(raw || '[]')
    return Array.isArray(parsed)
      ? parsed.filter((row) => Number(row?.time) > 0 && Number(row?.totalValue) > 0).slice(-240)
      : []
  } catch {
    return []
  }
}

function saveAccountHistory() {
  try {
    localStorage.setItem(ACCOUNT_HISTORY_KEY, JSON.stringify(accountHistory.value.slice(-240)))
  } catch {}
}

function loadResetEpoch() {
  try {
    const v = Number(localStorage.getItem(RESET_EPOCH_KEY))
    return Number.isFinite(v) && v > 0 ? v : 0
  } catch {
    return 0
  }
}

function saveResetEpoch() {
  try {
    if (resetEpoch.value > 0) localStorage.setItem(RESET_EPOCH_KEY, String(resetEpoch.value))
    else localStorage.removeItem(RESET_EPOCH_KEY)
  } catch {}
}

function recordAccountSnapshot(force = false) {
  const next = appendAccountSnapshot(accountHistory.value, accountValuation.value, Date.now(), { force })
  if (next.length !== accountHistory.value.length) {
    accountHistory.value = next
    saveAccountHistory()
    nextTick(renderAccountChart)
  }
}

function syncBalancePriceStreams() {
  const symbolList = symbols.value.map((s) => s.symbol)
  const neededAssets = new Set(assetsNeedingUsdtTicker(balances.value, symbolList))

  for (const [asset, unsubscribe] of balancePriceUnsubs.entries()) {
    if (!neededAssets.has(asset)) {
      try { unsubscribe() } catch {}
      balancePriceUnsubs.delete(asset)
      const symbol = `${asset}USDT`
      if (balanceTickerPrices.value[symbol] != null) {
        const next = { ...balanceTickerPrices.value }
        delete next[symbol]
        balanceTickerPrices.value = next
      }
    }
  }

  for (const asset of neededAssets) {
    if (balancePriceUnsubs.has(asset)) continue
    const symbol = `${asset}USDT`
    const unsubscribe = subscribeTicker(symbol, (quote) => {
      balanceTickerPrices.value = { ...balanceTickerPrices.value, [symbol]: quote.price }
      recordAccountSnapshot()
    })
    balancePriceUnsubs.set(asset, unsubscribe)
  }
}

function disposeBalancePriceStreams() {
  for (const unsubscribe of balancePriceUnsubs.values()) {
    try { unsubscribe() } catch {}
  }
  balancePriceUnsubs.clear()
}

// ---- 图表 ----
const chartEl = ref(null)
const accountChartEl = ref(null)
let chart = null
let datafeed = null
let accountChart = null
const chartMarkerStatus = ref({ ok: false, count: 0, reason: '' })
const accountEquityIndicatorStatus = ref({ ok: false, count: 0, markerCount: 0, reason: '' })
let markerSyncTimer = null
let accountEquitySyncTimer = null

const PERIODS = [
  { multiplier: 1, timespan: 'minute', text: '1m' },
  { multiplier: 5, timespan: 'minute', text: '5m' },
  { multiplier: 15, timespan: 'minute', text: '15m' },
  { multiplier: 1, timespan: 'hour', text: '1h' },
  { multiplier: 4, timespan: 'hour', text: '4h' },
  { multiplier: 1, timespan: 'day', text: '1D' },
  { multiplier: 1, timespan: 'week', text: '1W' },
]

function symbolInfo(ticker) {
  const s = symbols.value.find((x) => x.symbol === ticker)
  return {
    ticker,
    name: s?.name_zh || ticker,
    shortName: ticker.replace('USDT', ''),
    exchange: 'Binance', market: 'spot',
    pricePrecision: 2, volumePrecision: 4, priceCurrency: 'USDT', type: 'ADRC',
  }
}

function initChart() {
  if (!chartEl.value || chart) return
  datafeed = new BinanceDatafeed()
  chart = new KLineChartPro({
    container: chartEl.value,
    locale: 'zh-CN',
    theme: 'dark',
    symbol: symbolInfo(form.symbol),
    period: { multiplier: 1, timespan: 'hour', text: '1h' },
    periods: PERIODS,
    mainIndicators: ['MA'],
    subIndicators: ['VOL'],
    datafeed,
  })
  scheduleChartMarkerSync()
  scheduleAccountEquityIndicatorSync()
}

function changeSymbol(ticker) {
  form.symbol = ticker
  pct.value = 0
  exchangeTrades.value = []
  exchangeTradesError.value = ''
  expandedOrderIds.value = new Set()
  if (chart) chart.setSymbol(symbolInfo(ticker))
  scheduleChartMarkerSync()
  scheduleAccountEquityIndicatorSync()
  watchPrice(ticker)
  loadSymbolFilters(ticker)
  loadExchangeTrades()
  loadAccountExchangeTrades(false)
  recordAccountSnapshot()
}

function isOrderExpanded(key) {
  return expandedOrderIds.value.has(key)
}

function toggleOrderExpanded(key) {
  const next = new Set(expandedOrderIds.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedOrderIds.value = next
}

// 下单实际用的币种: 以图表当前展示的为准 (Pro 内置搜索也能改)
function activeSymbol() {
  try { return chart?.getSymbol()?.ticker || form.symbol } catch { return form.symbol }
}

function syncChartTradeMarkers() {
  try {
    const result = syncTradeOverlays(chart, chartTradeMarkers.value)
    chartMarkerStatus.value = result.ok
      ? { ok: true, count: result.count || 0, reason: '' }
      : { ok: false, count: 0, reason: result.reason || 'unknown' }
  } catch {
    chartMarkerStatus.value = { ok: false, count: 0, reason: 'sync-error' }
  }
}

function syncChartAccountEquityIndicator() {
  try {
    const result = syncAccountEquityIndicator(chart, accountEquityCurve.value, chartTradeMarkers.value)
    accountEquityIndicatorStatus.value = result.ok
      ? { ok: true, count: result.count || 0, markerCount: result.markerCount || 0, reason: '' }
      : { ok: false, count: 0, markerCount: 0, reason: result.reason || 'unknown' }
  } catch {
    accountEquityIndicatorStatus.value = { ok: false, count: 0, markerCount: 0, reason: 'sync-error' }
  }
}

function renderAccountChart() {
  const el = accountChartEl.value
  if (!el) return
  if (!accountChart || accountChart.getDom() !== el) {
    try { accountChart?.dispose() } catch {}
    accountChart = echarts.init(el, null, { renderer: 'canvas' })
  }

  const data = accountEquityCurve.value.map((row) => [row.time, row.totalValue])
  accountChart.setOption({
    animation: false,
    grid: { left: 8, right: 12, top: 12, bottom: 20, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#12161f',
      borderColor: '#2b3139',
      textStyle: { color: '#eaecef' },
      valueFormatter: (value) => `${Number(value).toFixed(2)} USDT`,
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#2b3139' } },
      axisLabel: { color: '#848e9c', fontSize: 10 },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisLabel: { color: '#848e9c', fontSize: 10 },
      splitLine: { lineStyle: { color: '#252b36', type: 'dashed' } },
    },
    series: [{
      name: '账户总资产',
      type: 'line',
      data,
      smooth: true,
      showSymbol: data.length < 12,
      symbolSize: 5,
      lineStyle: { width: 2, color: '#f0b90b' },
      itemStyle: { color: '#f0b90b' },
      areaStyle: { color: 'rgba(240, 185, 11, 0.08)' },
    }],
  }, true)
}

function scheduleChartMarkerSync() {
  if (markerSyncTimer) clearTimeout(markerSyncTimer)
  syncChartTradeMarkers()
  markerSyncTimer = setTimeout(() => {
    syncChartTradeMarkers()
    markerSyncTimer = setTimeout(syncChartTradeMarkers, 1200)
  }, 300)
}

function scheduleAccountEquityIndicatorSync() {
  if (accountEquitySyncTimer) clearTimeout(accountEquitySyncTimer)
  syncChartAccountEquityIndicator()
  accountEquitySyncTimer = setTimeout(() => {
    syncChartAccountEquityIndicator()
    accountEquitySyncTimer = setTimeout(syncChartAccountEquityIndicator, 1200)
  }, 300)
}

// ---- 数据加载 ----
function dismissToast(id) {
  toasts.value = toasts.value.filter((t) => t.id !== id)
}
function flash(type, text) {
  const id = ++toastSeq
  toasts.value.push({ id, type, text })
  // 错误停留久一点, 其余自动消失
  setTimeout(() => dismissToast(id), type === 'error' ? 6000 : 3500)
}

function normalizedSymbol(value) {
  return String(value || '').trim().toUpperCase()
}

function accountHistorySymbolCandidates() {
  const knownSymbols = new Set(symbols.value.map((item) => normalizedSymbol(item?.symbol)).filter(Boolean))
  const candidates = new Set(knownSymbols)

  if (form.symbol) candidates.add(normalizedSymbol(form.symbol))

  for (const trade of localTrades.value) {
    const symbol = normalizedSymbol(trade?.symbol)
    if (symbol) candidates.add(symbol)
  }

  for (const balance of balances.value) {
    const asset = String(balance?.asset || '').trim().toUpperCase()
    const total = Number(balance?.total ?? (Number(balance?.free) || 0) + (Number(balance?.locked) || 0))
    if (!asset || total <= 0 || STABLE_ASSETS.has(asset)) continue
    const symbol = `${asset}USDT`
    if (!knownSymbols.size || knownSymbols.has(symbol)) candidates.add(symbol)
  }

  return [...candidates].filter(Boolean).sort()
}

function mergeSymbolTrades(results) {
  const byKey = new Map()
  const tradedSymbols = new Set()
  const failedSymbols = []

  for (const result of results) {
    if (result.status !== 'fulfilled') {
      if (result.reason?.symbol) failedSymbols.push(result.reason.symbol)
      continue
    }

    const { symbol, data } = result.value
    if (!data?.ok) {
      failedSymbols.push(symbol)
      continue
    }

    const trades = Array.isArray(data.trades) ? data.trades : []
    if (trades.length) tradedSymbols.add(symbol)
    for (const trade of trades) {
      const id = trade?.id ?? trade?.tradeId ?? ''
      const key = `${symbol}:${id}:${trade?.orderId ?? ''}:${trade?.time ?? ''}:${trade?.price ?? ''}:${trade?.qty ?? ''}`
      byKey.set(key, { ...trade, symbol })
    }
  }

  const trades = [...byKey.values()].sort((a, b) => (Number(a.time) || 0) - (Number(b.time) || 0))
  return {
    trades,
    tradedSymbols: [...tradedSymbols].sort(),
    failedSymbols,
  }
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const c = await getTradeConnectivity()
    conn.value = c.data
  } catch (e) {
    error.value = e.message; loading.value = false; return
  }
  const jobs = [
    getTradeStatus().then((s) => { status.value = s.data }).catch(() => {}),
    loadTrades(),
    loadLiveStatus(true),
  ]
  if (connected.value) jobs.push(loadAccount(), loadOpenOrders(), loadExchangeTrades(), loadAccountExchangeTrades(true))
  await Promise.allSettled(jobs)
  lastDataRefreshAt.value = new Date()
  loading.value = false
}

// silent=true 用于后台轮询, 不弹 toast、失败时保留旧值避免闪烁
async function loadAccount(silent = false) {
  try {
    const r = await getTradeAccount()
    if (r.data?.ok) {
      balances.value = r.data.balances || []
      syncBalancePriceStreams()
      recordAccountSnapshot(true)
    }
    else if (!silent && r.data?.error) flash('error', `余额: ${r.data.error}`)
  } catch (e) { if (!silent) flash('error', `余额加载失败: ${e.message}`) }
}

async function loadOpenOrders(silent = false) {
  try {
    const r = await getOpenOrders()
    if (r.data?.ok) openOrders.value = r.data.orders || []
    else if (!silent && r.data?.error) flash('error', `委托: ${r.data.error}`)
  } catch (e) { if (!silent) flash('error', `委托加载失败: ${e.message}`) }
}

async function loadTrades() {
  try {
    const t = await listTrades('simulation', 50)
    localTrades.value = t.data.trades
    scheduleChartMarkerSync()
    scheduleAccountEquityIndicatorSync()
  } catch (e) { tradesError.value = e.message }
}

async function loadExchangeTrades() {
  if (!connected.value) return
  try {
    const t = await getMyTrades(form.symbol, 1000)
    if (t.data?.ok) {
      exchangeTrades.value = (t.data.trades || []).map((trade) => ({ ...trade, symbol: form.symbol }))
      exchangeTradesError.value = ''
    } else if (t.data?.error) {
      exchangeTradesError.value = t.data.error
    }
  } catch (e) {
    exchangeTradesError.value = e.message
  }
}

async function loadAccountExchangeTrades(force = false) {
  if (!connected.value || accountExchangeTradesLoading.value) return
  if (accountExchangeTradesLoaded.value && !force) return

  const candidates = accountHistorySymbolCandidates()
  if (!candidates.length) return

  accountExchangeTradesLoading.value = true
  try {
    const results = await Promise.allSettled(candidates.map(async (symbol) => {
      try {
        const response = await getMyTrades(symbol, 1000)
        return { symbol, data: response.data }
      } catch (error) {
        error.symbol = symbol
        throw error
      }
    }))
    const merged = mergeSymbolTrades(results)
    accountExchangeTrades.value = merged.trades
    accountExchangeTradeSymbols.value = merged.tradedSymbols
    accountExchangeTradesLoaded.value = true
    accountExchangeTradesError.value = merged.failedSymbols.length
      ? `部分币对成交加载失败: ${merged.failedSymbols.slice(0, 5).join(', ')}${merged.failedSymbols.length > 5 ? '...' : ''}`
      : ''
    nextTick(renderAccountChart)
    scheduleAccountEquityIndicatorSync()
  } catch (e) {
    accountExchangeTradesError.value = e.message
  } finally {
    accountExchangeTradesLoading.value = false
  }
}

// 后台轮询: 页面可见且已连接时, 每 5s 刷新委托/余额/记录
let pollTimer = null
let polling = false
async function refreshDynamic() {
  if (polling || document.hidden || !connected.value) return
  polling = true
  try {
    await Promise.allSettled([loadOpenOrders(true), loadAccount(true), loadTrades(), loadExchangeTrades(), loadLiveStatus(true)])
    lastDataRefreshAt.value = new Date()
  }
  finally { polling = false }
}

async function submitOrder() {
  const sym = activeSymbol()
  if (!sym || !form.quantity) return flash('error', '请填写币种和数量')
  if (form.type === 'LIMIT' && !form.price) return flash('error', 'LIMIT 单需要填写价格')
  // 提前拦余额不足 (卖出量 > 持有, 常因上次买入被手续费吃掉零头)
  if (form.side === 'SELL' && Number(form.quantity) > availFree.value + 1e-12) {
    return flash('error', `${baseAsset.value} 不足: 可用 ${fmt(availFree.value, 6)}, 想卖 ${form.quantity}（点「全部」按可用量卖出）`)
  }
  if (form.side === 'BUY' && form.type === 'LIMIT' && estCost.value > availFree.value + 1e-9) {
    return flash('error', `USDT 不足: 可用 ${fmt(availFree.value, 2)}, 本单约需 ${fmt(estCost.value, 2)}`)
  }
  submitting.value = true
  try {
    const payload = {
      symbol: sym, side: form.side, type: form.type,
      quantity: form.quantity, time_in_force: form.time_in_force,
      price: form.type === 'MARKET' ? null : form.price,
    }
    const r = await placeOrder(payload)
    if (r.data?.ok) {
      const o = r.data.order
      flash('success', `下单成功: ${sym} #${o.orderId} ${o.status || ''}`)
      pct.value = 0
      await Promise.allSettled([loadOpenOrders(), loadAccount(), loadTrades(), loadExchangeTrades(), loadAccountExchangeTrades(true)])
      lastDataRefreshAt.value = new Date()
    } else {
      flash('error', r.data?.error || '下单失败')
    }
  } catch (e) { flash('error', e.message) } finally { submitting.value = false }
}

async function doCancel(o) {
  try {
    const r = await cancelOrder(o.symbol, o.orderId)
    if (r.data?.ok) {
      flash('success', `已撤单 #${o.orderId}`)
      await Promise.allSettled([loadOpenOrders(), loadAccount(), loadTrades(), loadExchangeTrades(), loadAccountExchangeTrades(true)])
      lastDataRefreshAt.value = new Date()
    } else { flash('error', r.data?.error || '撤单失败') }
  } catch (e) { flash('error', e.message) }
}

// ---- 沙盒重置: 一键平仓 + 清本地 ----
// 弹窗预览: 将撤的挂单数 / 将卖出的持仓 / 预估卖不掉的 dust (后端按 minNotional 最终判定)
const resetPreview = computed(() => {
  const positions = positionRows.value.filter(
    (r) => !STABLE_ASSETS.has(String(r.asset || '').toUpperCase()) && Number(r.total) > 0
  )
  const dust = positions.filter((r) => r.priced && r.value > 0 && r.value < DUST_USDT)
  const sellable = positions.filter((r) => !(r.priced && r.value > 0 && r.value < DUST_USDT))
  return { orders: openOrders.value.length, sellable, dust }
})

function openResetModal() {
  if (!connected.value) return flash('error', '未连接沙盒账户, 无法重置')
  resetReport.value = null
  showResetModal.value = true
}

function closeResetModal() {
  if (resetting.value) return
  showResetModal.value = false
}

async function confirmReset() {
  if (resetting.value) return
  resetting.value = true
  try {
    const r = await resetSandbox()
    const rep = r.data || {}
    resetReport.value = rep

    // 设置重置时间点 (优先用服务器对齐时间, 略加缓冲, 确保平仓那几笔旧成交被过滤)
    resetEpoch.value = Math.max(Number(rep.reset_at) || 0, Date.now()) + 1000
    saveResetEpoch()

    // 清本地派生状态: 审计记录 / localStorage 资产快照 / 已加载的币安成交
    localTrades.value = []
    accountHistory.value = []
    saveAccountHistory()
    exchangeTrades.value = []
    accountExchangeTrades.value = []
    accountExchangeTradeSymbols.value = []
    accountExchangeTradesLoaded.value = false

    const soldN = (rep.sold || []).length
    const dustN = (rep.skipped_dust || []).length
    const failN = (rep.failed || []).length
    flash(failN ? 'error' : 'success',
      `沙盒重置完成: 撤单 ${rep.cancelled || 0} · 卖出 ${soldN} · dust ${dustN}${failN ? ` · 失败 ${failN}` : ''}`)

    await loadAll()
  } catch (e) {
    flash('error', `重置失败: ${e.message}`)
    resetReport.value = { ok: false, failed: [{ step: 'request', error: e.message }] }
  } finally {
    resetting.value = false
  }
}

// ---- 策略实盘: 加载 / 启动 / 停止 ----
async function loadStrategies() {
  try {
    const r = await getStrategies()
    strategies.value = r.data?.strategies || []
    if (!liveForm.strategyId && strategies.value.length) liveForm.strategyId = strategies.value[0].id
  } catch (e) { /* 列表失败不阻断页面 */ }
}

async function loadLiveStatus(silent = false) {
  try {
    const r = await getLiveStatus()
    if (r.data) live.value = r.data
  } catch (e) { if (!silent) flash('error', `实盘状态加载失败: ${e.message}`) }
}

function openLiveConfirm() {
  if (!connected.value) return flash('error', '未连接沙盒账户, 无法启动')
  if (!liveForm.strategyId) return flash('error', '请先选择策略')
  showLiveConfirm.value = true
}

async function confirmLiveStart() {
  if (liveStarting.value) return
  liveStarting.value = true
  try {
    const r = await startLive({
      strategy_id: liveForm.strategyId,
      symbol: liveForm.symbol,
      timeframe: liveForm.timeframe,
      params: {},
    })
    if (r.data?.ok) {
      live.value = r.data.status || live.value
      showLiveConfirm.value = false
      flash('success', `已启动: ${selectedStrategyName.value} · ${liveForm.symbol} · ${liveForm.timeframe}`)
    } else {
      flash('error', r.data?.error || '启动失败')
    }
  } catch (e) {
    flash('error', `启动失败: ${e.message}`)
  } finally {
    liveStarting.value = false
  }
}

async function stopLiveRun() {
  if (liveStopping.value) return
  liveStopping.value = true
  try {
    const r = await stopLive(false)
    if (r.data?.ok) {
      live.value = r.data.status || { running: false, logs: [] }
      flash('success', '已停止策略实盘')
    } else {
      flash('error', r.data?.error || '停止失败')
    }
  } catch (e) {
    flash('error', `停止失败: ${e.message}`)
  } finally {
    liveStopping.value = false
  }
}

function pctText(v) {
  const n = Number(v)
  return Number.isFinite(n) && n > 0 ? `${(n * 100).toFixed(1)}%` : '关'
}

function fmt(n, d = 4) { const v = Number(n); return Number.isFinite(v) ? v.toFixed(d) : '-' }
function assetQtyDigits(asset) {
  return STABLE_ASSETS.has(String(asset || '').toUpperCase()) ? 2 : 6
}
function assetPriceDigits(row) {
  const price = Number(row?.price)
  return price > 0 && price < 1 ? 8 : 2
}
function fmtAllocation(row) {
  const value = Number(row?.allocation)
  return value > 0 ? `${(value * 100).toFixed(1)}%` : '未估值'
}
function allocationWidth(row) {
  const value = Number(row?.allocation)
  return `${Math.max(0, Math.min(100, value * 100))}%`
}
function fmtMetricMoney(value, digits = 2) {
  const v = Number(value)
  if (!Number.isFinite(v)) return '-'
  return `${v > 0 ? '+' : ''}${v.toFixed(digits)}`
}
function fmtUnsignedPct(value, digits = 1) {
  const v = Number(value)
  return Number.isFinite(v) && v > 0 ? `${(v * 100).toFixed(digits)}%` : '-'
}
function fmtPayoffRatio(metrics) {
  if (metrics?.winCount > 0 && metrics?.lossCount === 0) return '∞'
  const value = Number(metrics?.payoffRatio)
  return Number.isFinite(value) && value > 0 ? value.toFixed(2) : '-'
}
function fmtSigned(n, d = 2) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '-'
  return `${v > 0 ? '+' : ''}${v.toFixed(d)}`
}
function fmtPct(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '-'
  return `${v > 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
}
function pnlClass(n) { return Number(n) >= 0 ? 'pos' : 'neg' }
function clock(value) { return formatClock(value) }
function ts(ms) { return ms ? new Date(Number(ms)).toLocaleString('zh-CN', { hour12: false }) : '-' }
function shortTs(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}

watch(chartTradeMarkers, () => {
  syncChartTradeMarkers()
  scheduleAccountEquityIndicatorSync()
}, { deep: true })

watch(accountValuation, () => {
  recordAccountSnapshot()
}, { deep: true })

watch(accountHistory, () => {
  nextTick(renderAccountChart)
}, { deep: true })

watch(accountEquityCurve, () => {
  nextTick(renderAccountChart)
  scheduleAccountEquityIndicatorSync()
}, { deep: true })

watch([balances, symbols], () => {
  syncBalancePriceStreams()
}, { deep: true })

onMounted(async () => {
  try {
    const r = await listSymbols(false)
    symbols.value = r.data?.symbols || []
  } catch {}
  liveForm.symbol = form.symbol
  loadStrategies()
  await nextTick()
  initChart()
  renderAccountChart()
  watchPrice(form.symbol)
  loadSymbolFilters(form.symbol)
  await loadAll()
  pollTimer = setInterval(refreshDynamic, 5000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (markerSyncTimer) clearTimeout(markerSyncTimer)
  if (accountEquitySyncTimer) clearTimeout(accountEquitySyncTimer)
  try { syncTradeOverlays(chart, []) } catch {}
  try { datafeed?.unsubscribe() } catch {}
  try { priceUnsub?.() } catch {}
  disposeBalancePriceStreams()
  try { accountChart?.dispose() } catch {}
  if (chartEl.value) chartEl.value.innerHTML = ''
  chart = null
  accountChart = null
})
</script>

<template>
  <div class="trade-page">
    <!-- 连通性状态条 -->
    <div class="card status-bar">
      <div class="status-left">
        <span class="dot" :class="connected ? 'on' : (conn.reachable ? 'warn' : 'off')"></span>
        <div>
          <div class="title">模拟盘 (Binance Demo Mode)</div>
          <div class="sub">
            <template v-if="connected">已连接沙盒账户 · Key {{ conn.api_key_masked }} · {{ conn.base_url }}</template>
            <template v-else-if="!configured">未配置凭据 — 设置 <code>BINANCE_DEMO_API_KEY</code> / <code>BINANCE_DEMO_API_SECRET</code> 后重启后端</template>
            <template v-else-if="conn.reachable">凭据无效: {{ conn.error }}</template>
            <template v-else>无法连接 demo 端点: {{ conn.error }}</template>
          </div>
        </div>
      </div>
      <div class="status-actions">
        <div class="time-chips">
          <span class="time-chip ws">WS {{ clock(lastWsUpdateAt) }}</span>
          <span class="time-chip">刷新 {{ clock(lastDataRefreshAt) }}</span>
        </div>
        <button class="btn ghost danger" @click="openResetModal"
                :disabled="loading || resetting || !connected"
                title="撤所有挂单 + 市价平仓换回 USDT + 清空本地记录">沙盒重置</button>
        <button class="btn ghost" @click="loadAll" :disabled="loading">刷新</button>
      </div>
    </div>


    <!-- 交易终端: 图表 + 下单面板 -->
    <div class="terminal">
      <div class="card chart-card">
        <div ref="chartEl" class="chart"></div>
        <div class="trade-markers">
          <div class="marker-head">
            <span>买卖标记</span>
            <small>
              {{ form.symbol }} ·
              K线 {{ chartMarkerStatus.ok ? chartMarkerStatus.count + ' 点' : '待挂载' }} ·
              资产副图 {{ accountEquityIndicatorStatus.ok ? accountEquityIndicatorStatus.count + ' 点' : '待挂载' }} ·
              最近 {{ tradeMarkers.length }} 笔
            </small>
          </div>
          <div v-if="tradeMarkers.length" class="marker-list">
            <button v-for="m in tradeMarkers" :key="m.id" type="button" class="trade-marker" :class="m.side"
                    :title="`${shortTs(m.created_at)} ${m.side === 'buy' ? '买入' : '卖出'} ${fmt(m.amount, 6)} @ ${fmt(m.price, 2)}`">
              <b>{{ m.side === 'buy' ? 'B' : 'S' }}</b>
              <span>{{ shortTs(m.created_at) }}</span>
              <em>{{ fmt(m.price, 2) }}</em>
              <strong v-if="m.side === 'sell'" :class="pnlClass(m.realizedPnl)">{{ fmtSigned(m.realizedPnl, 2) }}</strong>
            </button>
          </div>
          <div v-else class="marker-empty">当前币种暂无本地成交记录</div>
        </div>
      </div>

      <div class="card order-panel">
        <div class="op-row">
          <label class="grow">币种
            <select :value="form.symbol" @change="changeSymbol($event.target.value)">
              <option v-for="s in symbols" :key="s.symbol" :value="s.symbol">
                {{ s.symbol }} · {{ s.name_zh }}
              </option>
            </select>
          </label>
        </div>

        <div class="side-toggle">
          <button :class="{ active: form.side === 'BUY', buy: true }" @click="form.side = 'BUY'">买入</button>
          <button :class="{ active: form.side === 'SELL', sell: true }" @click="form.side = 'SELL'">卖出</button>
        </div>

        <fieldset :disabled="!connected" class="op-form">
          <label>类型
            <select v-model="form.type">
              <option value="LIMIT">限价 LIMIT</option>
              <option value="MARKET">市价 MARKET</option>
            </select>
          </label>
          <label v-if="form.type === 'LIMIT'">
            <span class="lbl-row">
              价格 (USDT)
              <button type="button" class="max-btn" @click="useMarketPrice"
                      :title="lastPrice ? '现价 ' + fmt(lastPrice, 2) : '等待行情'">
                市价 {{ lastPrice ? fmt(lastPrice, 2) : '…' }}
              </button>
            </span>
            <input v-model.number="form.price" type="number" step="any" placeholder="0.00" />
          </label>
          <label>
            <span class="lbl-row">
              数量 ({{ baseAsset }})
              <button v-if="form.side === 'SELL'" type="button" class="max-btn" @click="fillMax">全部</button>
            </span>
            <input v-model.number="form.quantity" type="number" step="any" />
          </label>
          <div class="avail">
            <span>可用 <b>{{ fmt(availFree, 6) }}</b> {{ availAsset }}</span>
            <span v-if="form.side === 'BUY' && estCost">约需 {{ fmt(estCost, 2) }} USDT</span>
          </div>

          <!-- 比例滑块: 按可用资金/持仓的百分比下单 -->
          <div class="pct-sizer">
            <input type="range" min="0" max="100" step="1" :value="pct"
                   @input="applyPct(+$event.target.value)" class="pct-slider"
                   :class="form.side === 'SELL' ? 'sell' : 'buy'" />
            <div class="pct-quick">
              <button v-for="p in [25, 50, 75, 100]" :key="p" type="button"
                      :class="{ active: pct === p }" @click="applyPct(p)">{{ p }}%</button>
            </div>
          </div>

          <button class="btn submit" :class="form.side === 'SELL' ? 'sell' : 'buy'"
                  @click="submitOrder" :disabled="submitting">
            {{ submitting ? '提交中...' : (form.side === 'BUY' ? '买入' : '卖出') }} {{ form.symbol.replace('USDT', '') }}
          </button>
        </fieldset>
        <p v-if="!connected" class="hint">连接沙盒账户后可下单</p>

        <div class="balances">
          <div class="bal-title">账户余额</div>
          <div v-if="!balances.length" class="bal-empty">— 无非零余额 —</div>
          <div v-for="b in balances" :key="b.asset" class="bal-row">
            <span class="asset">{{ b.asset }}</span>
            <span class="amt">{{ fmt(b.free, 4) }}</span>
            <span class="locked" v-if="b.locked">锁 {{ fmt(b.locked, 4) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="card pnl-panel">
      <div class="account-layout">
        <div class="account-main">
          <div class="panel-head">
            <div>
              <h3>账户总资产</h3>
              <p>
                基于 Binance 沙盒账户余额估值，手续费已体现在实际余额变化中 ·
                数据刷新 {{ clock(lastDataRefreshAt) }}
              </p>
            </div>
            <div class="panel-price">
              <span>总资产 USDT</span>
              <b>{{ accountValuation.totalValue ? fmt(accountValuation.totalValue, 2) : '-' }}</b>
            </div>
          </div>
          <div class="pnl-grid">
            <div class="pnl-item total">
              <span>总资产估值</span>
              <b>{{ fmt(accountValuation.totalValue, 2) }} <small>USDT</small></b>
            </div>
            <div class="pnl-item">
              <span>收益额</span>
              <b :class="pnlClass(accountPerformance.profitAmount)">
                {{ fmtMetricMoney(accountPerformance.profitAmount, 2) }} <small>USDT</small>
              </b>
            </div>
            <div class="pnl-item">
              <span>收益率</span>
              <b :class="pnlClass(accountPerformance.profitRate)">{{ fmtPct(accountPerformance.profitRate) }}</b>
            </div>
            <div class="pnl-item">
              <span>盈亏比</span>
              <b>{{ fmtPayoffRatio(accountPerformance) }}</b>
            </div>
            <div class="pnl-item">
              <span>期望 / 笔</span>
              <b :class="pnlClass(accountPerformance.expectancy)">
                {{ fmtMetricMoney(accountPerformance.expectancy, 2) }} <small>USDT</small>
              </b>
            </div>
            <div class="pnl-item">
              <span>Binance 订单/成交</span>
              <b>{{ exchangeOrderRows.length }} / {{ exchangeFillCount }}</b>
            </div>
          </div>
          <div class="account-chart-wrap">
            <div class="account-chart-head">
              <span>账户总资产变化</span>
              <small>{{ accountHistorySource }} · {{ accountHistoryCoverage }}</small>
            </div>
            <div v-if="accountExchangeTradesError" class="account-chart-warn">{{ accountExchangeTradesError }}</div>
            <div v-if="accountEquityCurve.length > 1" ref="accountChartEl" class="account-chart"></div>
            <div v-else class="account-chart-empty">等待更多账户或行情刷新后绘制曲线</div>
          </div>
        </div>

        <aside class="position-panel">
          <div class="position-head">
            <div>
              <h3>持仓信息</h3>
              <p>{{ positionRows.length }} 种资产 · {{ accountValuation.pricedAssetCount }} 种已估值</p>
            </div>
            <span>{{ accountValuation.totalValue ? fmt(accountValuation.totalValue, 2) : '-' }} USDT</span>
          </div>
          <div v-if="positionRows.length" class="position-list">
            <div
              v-for="row in positionRows"
              :key="row.asset"
              class="position-row"
              :class="{ active: row.asset === accountValuation.selectedAsset, unpriced: !row.priced }"
            >
              <div class="position-top">
                <div class="position-asset">
                  <b>{{ row.asset }}</b>
                  <span v-if="row.asset === accountValuation.selectedAsset">当前</span>
                  <span v-else-if="!row.priced">未估值</span>
                </div>
                <strong>{{ row.priced ? fmt(row.value, 2) : '-' }} <small>USDT</small></strong>
              </div>
              <div class="position-meta">
                <span>总量 {{ fmt(row.total, assetQtyDigits(row.asset)) }}</span>
                <span>{{ fmtAllocation(row) }}</span>
              </div>
              <div class="position-meta muted">
                <span>可用 {{ fmt(row.free, assetQtyDigits(row.asset)) }}</span>
                <span v-if="row.locked">锁定 {{ fmt(row.locked, assetQtyDigits(row.asset)) }}</span>
                <span v-else>价格 {{ row.priced ? fmt(row.price, assetPriceDigits(row)) : '-' }}</span>
              </div>
              <div class="position-bar"><span :style="{ width: allocationWidth(row) }"></span></div>
            </div>
          </div>
          <div v-else class="position-empty">暂无持仓</div>
        </aside>
      </div>
    </div>

    <!-- 策略实盘 -->
    <div class="card live-panel">
      <div class="section-head">
        <h3>
          策略实盘
          <span class="live-badge" :class="live.running ? 'on' : 'off'">{{ live.running ? '运行中' : '未运行' }}</span>
        </h3>
        <span v-if="live.running">{{ live.symbol }} · {{ live.timeframe }} · 刷新 {{ clock(lastDataRefreshAt) }}</span>
      </div>

      <!-- 未运行: 配置 + 启动 -->
      <div v-if="!live.running" class="live-config">
        <label>策略
          <select v-model.number="liveForm.strategyId">
            <option :value="null" disabled>选择策略…</option>
            <option v-for="s in strategies" :key="s.id" :value="s.id">
              {{ s.name }}{{ s.is_builtin ? '' : ' · 自定义' }}
            </option>
          </select>
        </label>
        <label>标的
          <select v-model="liveForm.symbol">
            <option v-for="s in symbols" :key="s.symbol" :value="s.symbol">{{ s.symbol }}</option>
          </select>
        </label>
        <label>周期
          <select v-model="liveForm.timeframe">
            <option v-for="tf in liveTimeframes" :key="tf" :value="tf">{{ tf }}</option>
          </select>
        </label>
        <button class="btn submit buy live-start" :disabled="!connected || !liveForm.strategyId || liveStarting"
                @click="openLiveConfirm">{{ liveStarting ? '启动中…' : '启动实盘' }}</button>
        <p v-if="!connected" class="hint live-hint">连接沙盒账户后可启动</p>
      </div>

      <!-- 运行中: 状态 + 日志 + 停止 -->
      <div v-else class="live-running">
        <div class="live-grid">
          <div class="live-item"><span>策略</span><b>{{ live.strategy_name }}</b></div>
          <div class="live-item"><span>持仓</span><b :class="live.position === 'long' ? 'pos' : ''">{{ live.position === 'long' ? '持有' : '空仓' }}</b></div>
          <div class="live-item"><span>最新信号</span><b>{{ live.last_signal == null ? '-' : (live.last_signal ? '持有' : '空仓') }}</b></div>
          <div class="live-item"><span>持仓均价</span><b>{{ live.entry_price ? fmt(live.entry_price, 2) : '-' }}</b></div>
          <div class="live-item"><span>现价</span><b>{{ live.last_price ? fmt(live.last_price, 2) : '-' }}</b></div>
          <div class="live-item"><span>止损 / 止盈</span><b>{{ pctText(live.stop_loss) }} / {{ pctText(live.take_profit) }}</b></div>
        </div>
        <div class="live-actions">
          <span class="live-last">{{ live.last_action || '等待信号…' }}</span>
          <button class="btn ghost danger" :disabled="liveStopping" @click="stopLiveRun">{{ liveStopping ? '停止中…' : '停止' }}</button>
        </div>
        <div v-if="live.error" class="live-error">⚠️ {{ live.error }}</div>
        <div v-if="(live.logs || []).length" class="live-log">
          <div v-for="(l, i) in [...(live.logs || [])].reverse()" :key="i" class="live-log-row">
            <span>{{ shortTs(l.time) }}</span><span>{{ l.msg }}</span>
          </div>
        </div>
      </div>
    </div>

    <StateView :loading="loading" :error="error" />

    <!-- 当前委托 + 本地记录 并排一行 -->
    <div class="tables-row">
      <div class="card">
        <div class="section-head">
          <h3>当前委托 ({{ openOrders.length }})</h3>
          <span>刷新 {{ clock(lastDataRefreshAt) }}</span>
        </div>
        <StateView :empty="!openOrders.length" empty-text="无挂单" empty-icon="📋" />
        <div v-if="openOrders.length" class="table-scroll">
          <table>
            <thead><tr>
              <th>时间</th><th>币种</th><th>方向</th><th>类型</th>
              <th>价格</th><th>数量</th><th>已成交</th><th>状态</th><th></th>
            </tr></thead>
            <tbody>
              <tr v-for="o in openOrders" :key="o.orderId">
                <td>{{ ts(o.time) }}</td>
                <td class="sym-cell">{{ o.symbol }}</td>
                <td :class="o.side === 'BUY' ? 'pos' : 'neg'">{{ o.side }}</td>
                <td>{{ o.type }}</td>
                <td>{{ fmt(o.price) }}</td>
                <td>{{ fmt(o.origQty) }}</td>
                <td>{{ fmt(o.executedQty) }}</td>
                <td>{{ o.status }}</td>
                <td><button class="btn ghost sm" @click="doCancel(o)">撤单</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="section-head">
          <h3>Binance 成交记录 ({{ exchangeOrderRows.length }} 单 / {{ exchangeFillCount }} 笔)</h3>
          <span>刷新 {{ clock(lastDataRefreshAt) }}</span>
        </div>
        <div v-if="exchangeTradesError" class="card-err">
          加载失败: {{ exchangeTradesError }}
          <span v-if="exchangeTradesError.includes('500')"> —— 多为后端未重启, 请重启后端</span>
        </div>
        <StateView v-else :empty="!exchangeOrderRows.length" empty-text="当前币种暂无成交" empty-icon="📒" />
        <div v-if="exchangeOrderRows.length" class="table-scroll">
          <table>
            <thead><tr>
              <th>时间</th><th>方向</th><th>价格</th><th>数量</th><th>成交额</th>
              <th>手续费</th><th>流动性</th><th>订单</th>
            </tr></thead>
            <tbody>
              <template v-for="order in exchangeOrderRows" :key="order.key">
                <tr class="order-row" :class="{ expanded: isOrderExpanded(order.key) }">
                  <td>
                    <div class="order-time-cell">
                      <button
                        v-if="order.fillCount > 1"
                        type="button"
                        class="expand-btn"
                        data-testid="exchange-order-expand"
                        :aria-expanded="isOrderExpanded(order.key)"
                        @click="toggleOrderExpanded(order.key)"
                      >
                        {{ isOrderExpanded(order.key) ? '▾' : '▸' }}
                      </button>
                      <span v-else class="expand-spacer"></span>
                      <span>{{ ts(order.time) }}</span>
                    </div>
                  </td>
                  <td :class="order.side === 'buy' ? 'pos' : 'neg'">{{ order.side === 'buy' ? '买入' : '卖出' }}</td>
                  <td>{{ fmt(order.price) }}</td>
                  <td>{{ fmt(order.qty, 6) }}</td>
                  <td>{{ fmt(order.quoteQty, 2) }}</td>
                  <td>{{ order.commissionText }}</td>
                  <td>{{ order.liquidity }}</td>
                  <td class="note order-note">
                    <span>#{{ order.orderId || order.id }}</span>
                    <span v-if="order.fillCount > 1" class="fill-count">{{ order.fillCount }} 笔</span>
                  </td>
                </tr>
                <template v-if="isOrderExpanded(order.key)">
                  <tr v-for="fill in order.fills" :key="`${order.key}-${fill.id}`" class="fill-row">
                    <td>
                      <div class="order-time-cell fill-time">
                        <span class="fill-branch">↳</span>
                        <span>{{ ts(fill.time) }}</span>
                      </div>
                    </td>
                    <td :class="fill.side === 'buy' ? 'pos' : 'neg'">{{ fill.side === 'buy' ? '买入' : '卖出' }}</td>
                    <td>{{ fmt(fill.price) }}</td>
                    <td>{{ fmt(fill.qty, 6) }}</td>
                    <td>{{ fmt(fill.quoteQty, 2) }}</td>
                    <td>{{ fmt(fill.commission, 8) }} {{ fill.commissionAsset || '-' }}</td>
                    <td>{{ fill.isMaker ? 'Maker' : 'Taker' }}</td>
                    <td class="note">fill #{{ fill.id }}</td>
                  </tr>
                </template>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 沙盒重置: 确认预览 / 执行战报 -->
    <div v-if="showResetModal" class="reset-mask" @click.self="closeResetModal">
      <div class="reset-modal">
        <!-- 阶段一: 确认预览 -->
        <template v-if="!resetReport">
          <h3>沙盒重置</h3>
          <p class="reset-sub">将对当前 Binance 沙盒账户执行以下不可逆操作:</p>
          <ul class="reset-plan">
            <li>撤销全部挂单 · <b>{{ resetPreview.orders }}</b> 个</li>
            <li>市价卖出非 USDT 持仓换回 USDT · <b>{{ resetPreview.sellable.length }}</b> 项</li>
            <li>清空本地交易记录与界面统计</li>
          </ul>
          <div v-if="resetPreview.sellable.length" class="reset-list">
            <div v-for="r in resetPreview.sellable" :key="r.asset" class="reset-row">
              <span>{{ r.asset }}</span>
              <span>{{ fmt(r.total, assetQtyDigits(r.asset)) }}</span>
              <span>{{ r.priced ? '≈ ' + fmt(r.value, 2) + ' USDT' : '未估值' }}</span>
            </div>
          </div>
          <div v-else class="reset-empty">当前无可平仓持仓</div>

          <div v-if="resetPreview.dust.length" class="reset-dust">
            预计卖不掉的 dust（{{ resetPreview.dust.length }} 项, 市值过低）:
            {{ resetPreview.dust.map(d => d.asset).join('、') }}
          </div>

          <ul class="reset-warn">
            <li>真实不可逆的 testnet 成交, 会产生手续费</li>
            <li>金额不会回到初始本金（取决于卖出所得）</li>
            <li>Binance 服务器侧成交记录删不掉, 仅本地记录与界面会重置</li>
          </ul>

          <div class="reset-actions">
            <button class="btn ghost" @click="closeResetModal" :disabled="resetting">取消</button>
            <button class="btn submit sell" @click="confirmReset" :disabled="resetting">
              {{ resetting ? '执行中…' : '确定重置' }}
            </button>
          </div>
        </template>

        <!-- 阶段二: 执行战报 -->
        <template v-else>
          <h3>重置完成</h3>
          <div class="reset-report">
            <div class="rr-item"><span>撤销挂单</span><b>{{ resetReport.cancelled || 0 }}</b></div>
            <div class="rr-item"><span>成功卖出</span><b>{{ (resetReport.sold || []).length }}</b></div>
            <div class="rr-item"><span>跳过 dust</span><b>{{ (resetReport.skipped_dust || []).length }}</b></div>
            <div class="rr-item"><span>失败</span><b :class="{ neg: (resetReport.failed || []).length }">{{ (resetReport.failed || []).length }}</b></div>
            <div class="rr-item"><span>清本地</span><b>{{ resetReport.local_cleared || 0 }}</b></div>
          </div>
          <div v-if="(resetReport.sold || []).length" class="reset-list">
            <div v-for="s in resetReport.sold" :key="s.symbol" class="reset-row">
              <span>卖出 {{ s.asset }}</span>
              <span>{{ fmt(s.qty, 6) }}</span>
              <span class="pos">+{{ fmt(s.quote, 2) }} USDT</span>
            </div>
          </div>
          <div v-if="(resetReport.skipped_dust || []).length" class="reset-dust">
            残留 dust: {{ resetReport.skipped_dust.map(d => d.asset).join('、') }}（市值低于币安最小名义额, 无法市价卖出）
          </div>
          <div v-if="(resetReport.failed || []).length" class="reset-fail">
            <div v-for="(f, i) in resetReport.failed" :key="i">✗ {{ f.step }} {{ f.symbol || '' }}: {{ f.error }}</div>
          </div>
          <div class="reset-actions">
            <button class="btn submit" @click="closeResetModal">关闭</button>
          </div>
        </template>
      </div>
    </div>

    <!-- 启动策略实盘确认 -->
    <div v-if="showLiveConfirm" class="reset-mask" @click.self="showLiveConfirm = false">
      <div class="reset-modal">
        <h3>启动策略实盘</h3>
        <p class="reset-sub">将在 Binance 沙盒账户上按策略信号自动下真实市价单:</p>
        <ul class="reset-plan">
          <li>策略 · <b>{{ selectedStrategyName }}</b></li>
          <li>标的 / 周期 · <b>{{ liveForm.symbol }} / {{ liveForm.timeframe }}</b></li>
          <li>每根 K 线收盘评估信号, 持有 ↔ 空仓 自动切换</li>
          <li>止损止盈按策略 DSL 执行 (仅运行期间生效)</li>
        </ul>
        <ul class="reset-warn">
          <li>真实不可逆的 testnet 成交, 会产生手续费</li>
          <li>行情价 (公开 API) 与成交价 (demo) 可能有偏差</li>
          <li>同一时间只跑一个策略; 后端重启不自动续跑</li>
        </ul>
        <div class="reset-actions">
          <button class="btn ghost" @click="showLiveConfirm = false" :disabled="liveStarting">取消</button>
          <button class="btn submit buy" @click="confirmLiveStart" :disabled="liveStarting">
            {{ liveStarting ? '启动中…' : '确定启动' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 左下角气泡通知 -->
    <transition-group name="toast" tag="div" class="toast-wrap">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type" @click="dismissToast(t.id)">
        <span class="toast-ico">{{ t.type === 'success' ? '✓' : '!' }}</span>
        <span>{{ t.text }}</span>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.trade-page { display: flex; flex-direction: column; gap: 16px; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 20px;
}
.card h3 { font-size: 15px; margin-bottom: 12px; }

/* 状态条 */
.status-bar { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; }
.status-left { display: flex; align-items: center; gap: 14px; }
.status-bar .title { font-weight: 600; }
.status-bar .sub { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.status-bar code { background: var(--bg); padding: 1px 5px; border-radius: 4px; font-size: 11px; color: var(--yellow); }
.status-actions { display: flex; align-items: center; gap: 12px; }
.time-chips { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.time-chip {
  display: inline-flex; align-items: center;
  min-height: 24px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-muted);
  font-family: 'Consolas', monospace;
  font-size: 11px;
  white-space: nowrap;
}
.time-chip.ws { color: var(--green); border-color: rgba(2, 192, 118, 0.32); }
.dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.dot.on { background: var(--green); box-shadow: 0 0 8px var(--green); }
.dot.warn { background: var(--yellow); }
.dot.off { background: var(--red); }

/* 左下角气泡通知 */
.toast-wrap {
  position: fixed; left: 20px; bottom: 20px; z-index: 9999;
  display: flex; flex-direction: column-reverse; gap: 10px;
  pointer-events: none;
}
.toast {
  pointer-events: auto; cursor: pointer;
  display: flex; align-items: center; gap: 10px;
  max-width: 360px; padding: 11px 14px; border-radius: 10px;
  font-size: 13px; line-height: 1.4;
  background: var(--bg-card); border: 1px solid var(--border);
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.toast-ico {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%;
  display: grid; place-items: center; font-size: 12px; font-weight: 700; color: #08130c;
}
.toast.success { border-color: var(--green); }
.toast.success .toast-ico { background: var(--green); }
.toast.error { border-color: var(--red); }
.toast.error .toast-ico { background: var(--red); color: #1a0608; }
/* 进出动画: 从左侧滑入, 淡出 */
.toast-enter-active, .toast-leave-active { transition: all 0.3s ease; }
.toast-enter-from { opacity: 0; transform: translateX(-20px); }
.toast-leave-to { opacity: 0; transform: translateX(-20px); }
.toast-leave-active { position: absolute; }

/* 终端布局: 图表 + 下单面板 */
.terminal { display: grid; grid-template-columns: 1fr 300px; gap: 16px; align-items: stretch; }
.chart-card { padding: 0; overflow: hidden; }
.chart { width: 100%; height: 650px; }
.trade-markers {
  border-top: 1px solid var(--border);
  padding: 10px 12px 12px;
  background: rgba(15, 18, 26, 0.72);
}
.marker-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.marker-head span { font-size: 12px; font-weight: 700; color: var(--text); }
.marker-head small { font-size: 11px; color: var(--text-muted); }
.marker-list { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 2px; }
.trade-marker {
  flex: 0 0 auto;
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 8px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 11px;
  cursor: default;
}
.trade-marker b {
  display: grid; place-items: center;
  width: 18px; height: 18px;
  border-radius: 50%;
  font-size: 11px;
  color: #06120b;
}
.trade-marker.buy { border-color: rgba(2, 192, 118, 0.38); }
.trade-marker.sell { border-color: rgba(246, 70, 93, 0.42); }
.trade-marker.buy b { background: var(--green); }
.trade-marker.sell b { background: var(--red); color: #1a0608; }
.trade-marker em { font-style: normal; color: var(--text); font-family: 'Consolas', monospace; }
.trade-marker strong { font-family: 'Consolas', monospace; font-size: 11px; }
.marker-empty { font-size: 12px; color: var(--text-muted); padding: 4px 0; }

/* 账户资产 */
.pnl-panel { padding: 16px 18px; }
.account-layout {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
  gap: 16px;
  align-items: stretch;
}
.account-main { min-width: 0; }
.panel-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 14px; }
.panel-head h3 { margin: 0 0 4px; }
.panel-head p { margin: 0; color: var(--text-muted); font-size: 12px; }
.panel-price { text-align: right; font-family: 'Consolas', monospace; }
.panel-price span { display: block; color: var(--text-muted); font-size: 11px; margin-bottom: 3px; }
.panel-price b { font-size: 18px; color: var(--yellow); }
.pnl-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.pnl-item {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 9px 10px;
  background: var(--bg);
}
.pnl-item span { display: block; color: var(--text-muted); font-size: 11px; margin-bottom: 6px; }
.pnl-item b {
  display: block;
  font-family: 'Consolas', monospace;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pnl-item.total { border-color: rgba(240, 185, 11, 0.42); }
.pnl-item small { margin-left: 4px; color: var(--text-muted); font-size: 11px; }
.account-chart-wrap {
  margin-top: 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  padding: 10px 12px 8px;
}
.account-chart-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 6px; }
.account-chart-head span { font-size: 12px; color: var(--text); font-weight: 700; }
.account-chart-head small { font-size: 11px; color: var(--text-muted); font-family: 'Consolas', monospace; }
.account-chart-warn {
  margin-bottom: 6px;
  color: var(--yellow);
  font-size: 11px;
}
.account-chart { width: 100%; height: 150px; }
.account-chart-empty {
  height: 86px;
  display: grid;
  place-items: center;
  color: var(--text-muted);
  font-size: 12px;
}
.position-panel {
  min-width: 0;
  border-left: 1px solid var(--border);
  padding-left: 16px;
  display: flex;
  flex-direction: column;
}
.position-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}
.position-head h3 { margin: 0 0 4px; font-size: 15px; }
.position-head p { margin: 0; color: var(--text-muted); font-size: 12px; }
.position-head > span {
  flex-shrink: 0;
  color: var(--yellow);
  font-family: 'Consolas', monospace;
  font-size: 12px;
  white-space: nowrap;
}
.position-list {
  min-height: 0;
  max-height: 330px;
  overflow-y: auto;
  padding-right: 2px;
}
.position-row {
  padding: 9px 0 10px;
  border-bottom: 1px solid var(--border);
}
.position-row:first-child { padding-top: 2px; }
.position-row.active .position-asset b { color: var(--yellow); }
.position-row.unpriced { opacity: 0.75; }
.position-top,
.position-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}
.position-asset {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.position-asset b {
  color: var(--text);
  font-family: 'Consolas', monospace;
  font-size: 13px;
}
.position-asset span {
  padding: 1px 5px;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-muted);
  font-size: 10px;
}
.position-top strong {
  min-width: 0;
  color: var(--text);
  font-family: 'Consolas', monospace;
  font-size: 13px;
  white-space: nowrap;
}
.position-top small { color: var(--text-muted); font-size: 10px; }
.position-meta {
  margin-top: 5px;
  color: var(--text-secondary);
  font-family: 'Consolas', monospace;
  font-size: 11px;
}
.position-meta.muted { color: var(--text-muted); }
.position-bar {
  height: 3px;
  margin-top: 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}
.position-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--yellow), rgba(2, 192, 118, 0.82));
}
.position-empty {
  flex: 1;
  display: grid;
  place-items: center;
  min-height: 180px;
  color: var(--text-muted);
  font-size: 12px;
}
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.section-head h3 { margin-bottom: 0; }
.section-head span { color: var(--text-muted); font-size: 11px; font-family: 'Consolas', monospace; white-space: nowrap; }

/* 下单面板 */
.order-panel { display: flex; flex-direction: column; gap: 14px; }
.op-row { display: flex; gap: 10px; }
.op-row .grow { flex: 1; }
.order-panel label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary); }
.order-panel select, .order-panel input {
  background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px 10px; color: var(--text); font-size: 13px; font-family: 'Consolas', monospace;
}
.side-toggle { display: flex; gap: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.side-toggle button {
  flex: 1; padding: 9px 0; background: var(--bg); color: var(--text-secondary);
  border: none; cursor: pointer; font-size: 14px; font-weight: 600;
}
.side-toggle button.buy.active { background: var(--green); color: #08130c; }
.side-toggle button.sell.active { background: var(--red); color: #1a0608; }
.op-form { border: none; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.op-form:disabled { opacity: 0.5; }
.lbl-row { display: flex; justify-content: space-between; align-items: center; }
.max-btn { background: transparent; border: 1px solid var(--border); color: var(--yellow); border-radius: 4px; padding: 1px 8px; font-size: 11px; cursor: pointer; }
.max-btn:hover { border-color: var(--yellow); }
.avail { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-secondary); margin-top: -4px; }
.avail b { color: var(--text); font-family: 'Consolas', monospace; }

/* 比例滑块 */
.pct-sizer { display: flex; flex-direction: column; gap: 8px; }
.pct-slider { -webkit-appearance: none; appearance: none; width: 100%; height: 4px; border-radius: 3px; background: var(--border); outline: none; cursor: pointer; }
.pct-slider::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 14px; height: 14px; border-radius: 50%; cursor: pointer; }
.pct-slider.buy::-webkit-slider-thumb { background: var(--green); }
.pct-slider.sell::-webkit-slider-thumb { background: var(--red); }
.pct-slider::-moz-range-thumb { width: 14px; height: 14px; border: none; border-radius: 50%; cursor: pointer; }
.pct-slider.buy::-moz-range-thumb { background: var(--green); }
.pct-slider.sell::-moz-range-thumb { background: var(--red); }
.pct-quick { display: flex; gap: 6px; }
.pct-quick button { flex: 1; padding: 5px 0; background: var(--bg); border: 1px solid var(--border); color: var(--text-secondary); border-radius: 5px; font-size: 11px; cursor: pointer; }
.pct-quick button:hover { border-color: var(--text-secondary); }
.pct-quick button.active { border-color: var(--yellow); color: var(--yellow); }
.btn {
  background: var(--bg); border: 1px solid var(--border); color: var(--text);
  padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;
}
.btn:hover { border-color: var(--text-secondary); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.sm { padding: 4px 10px; font-size: 12px; }
.btn.ghost { background: transparent; }
.btn.submit { padding: 11px 0; font-weight: 700; font-size: 14px; border: none; }
.btn.submit.buy { background: var(--green); color: #08130c; }
.btn.submit.sell { background: var(--red); color: #1a0608; }
.btn.ghost.danger { color: var(--red); border-color: color-mix(in srgb, var(--red) 45%, var(--border)); }
.btn.ghost.danger:hover:not(:disabled) { border-color: var(--red); }
.hint { font-size: 12px; color: var(--text-muted); }

/* 沙盒重置弹窗 */
.reset-mask {
  position: fixed; inset: 0; z-index: 200; display: flex; align-items: center; justify-content: center;
  background: rgba(0, 0, 0, 0.55); backdrop-filter: blur(2px); padding: 20px;
}
.reset-modal {
  width: 100%; max-width: 460px; max-height: 86vh; overflow-y: auto;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
  padding: 20px 22px; box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
}
.reset-modal h3 { margin: 0 0 10px; font-size: 17px; }
.reset-sub { margin: 0 0 8px; font-size: 13px; color: var(--text-secondary); }
.reset-plan { margin: 0 0 12px; padding-left: 18px; font-size: 13px; line-height: 1.9; }
.reset-plan b { color: var(--yellow); }
.reset-list {
  border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 12px;
  max-height: 200px; overflow-y: auto;
}
.reset-row {
  display: grid; grid-template-columns: 1fr auto auto; gap: 12px;
  padding: 7px 12px; font-family: 'Consolas', monospace; font-size: 12.5px;
  border-bottom: 1px solid var(--border);
}
.reset-row:last-child { border-bottom: none; }
.reset-row .pos { color: var(--green); }
.reset-empty { font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }
.reset-dust {
  font-size: 12px; color: var(--yellow); background: color-mix(in srgb, var(--yellow) 10%, transparent);
  border-radius: 6px; padding: 8px 10px; margin-bottom: 12px;
}
.reset-warn {
  margin: 0 0 16px; padding: 10px 10px 10px 26px; list-style: '⚠️ '; font-size: 12px; line-height: 1.8;
  color: var(--text-secondary); background: color-mix(in srgb, var(--red) 8%, transparent); border-radius: 8px;
}
.reset-fail { font-size: 12px; color: var(--red); margin-bottom: 12px; line-height: 1.7; word-break: break-all; }
.reset-report {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-bottom: 14px;
}
.rr-item {
  display: flex; flex-direction: column; gap: 4px; align-items: center;
  background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 10px 4px;
}
.rr-item span { font-size: 11px; color: var(--text-muted); }
.rr-item b { font-size: 18px; }
.rr-item b.neg { color: var(--red); }
.reset-actions { display: flex; justify-content: flex-end; gap: 10px; }
.reset-actions .btn.submit { padding: 9px 20px; }
@media (max-width: 560px) {
  .reset-report { grid-template-columns: repeat(2, 1fr); }
}

/* 策略实盘 */
.live-badge {
  font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; margin-left: 8px; vertical-align: middle;
}
.live-badge.on { background: color-mix(in srgb, var(--green) 18%, transparent); color: var(--green); }
.live-badge.off { background: var(--bg); color: var(--text-muted); border: 1px solid var(--border); }
.live-config { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.live-config label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary); }
.live-config select {
  background: var(--bg); border: 1px solid var(--border); color: var(--text);
  padding: 8px 10px; border-radius: 6px; font-size: 13px; min-width: 150px;
}
.live-start { padding: 9px 22px; }
.live-hint { width: 100%; margin: 0; }
.live-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 12px; }
.live-item {
  display: flex; flex-direction: column; gap: 4px;
  background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 9px 11px;
}
.live-item span { font-size: 11px; color: var(--text-muted); }
.live-item b { font-size: 14px; font-family: 'Consolas', monospace; }
.live-item b.pos { color: var(--green); }
.live-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.live-last { font-size: 13px; color: var(--text-secondary); }
.live-error { font-size: 12px; color: var(--red); margin-bottom: 10px; }
.live-log {
  max-height: 180px; overflow-y: auto; border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg); padding: 6px 0;
}
.live-log-row {
  display: grid; grid-template-columns: 110px 1fr; gap: 10px; padding: 3px 12px;
  font-family: 'Consolas', monospace; font-size: 12px; color: var(--text-secondary);
}
.live-log-row span:first-child { color: var(--text-muted); }
@media (max-width: 760px) {
  .live-grid { grid-template-columns: repeat(2, 1fr); }
}

/* 余额 */
.balances { border-top: 1px solid var(--border); padding-top: 12px; }
.bal-title { font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; }
.bal-empty { font-size: 12px; color: var(--text-muted); }
.bal-row { display: flex; align-items: baseline; gap: 8px; padding: 4px 0; font-family: 'Consolas', monospace; font-size: 13px; }
.bal-row .asset { color: var(--yellow); font-weight: 600; width: 64px; }
.bal-row .amt { flex: 1; text-align: right; }
.bal-row .locked { font-size: 11px; color: var(--text-muted); }

/* 表格 */
table { width: 100%; border-collapse: collapse; margin-top: 8px; }
th { text-align: left; padding: 9px 12px; background: var(--bg); color: var(--text-secondary); font-size: 11px; font-weight: 500; border-bottom: 1px solid var(--border); }
td { padding: 9px 12px; border-bottom: 1px solid var(--border); font-size: 13px; font-family: 'Consolas', monospace; }
.sym-cell { font-weight: 600; color: var(--yellow); }
.note { font-family: inherit; color: var(--text-secondary); font-size: 12px; }
.pos { color: var(--green); }
.neg { color: var(--red); }
.order-time-cell { display: flex; align-items: center; gap: 7px; min-width: 132px; }
.expand-btn {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  padding: 0;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}
.expand-btn:hover,
.expand-btn[aria-expanded="true"] {
  border-color: rgba(240, 185, 11, 0.6);
  color: var(--yellow);
}
.expand-spacer {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
}
.order-row.expanded td { background: rgba(240, 185, 11, 0.04); }
.fill-row td {
  background: rgba(255, 255, 255, 0.025);
  color: var(--text-secondary);
  font-size: 12px;
}
.fill-time { color: var(--text-secondary); }
.fill-branch {
  flex: 0 0 auto;
  width: 18px;
  text-align: center;
  color: var(--text-muted);
}
.fill-count {
  display: inline-flex;
  align-items: center;
  margin-left: 8px;
  padding: 1px 5px;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
}

/* 当前委托 + 本地记录 并排 */
.tables-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
.table-scroll { overflow-x: auto; }
.card-err { padding: 14px; border-radius: 8px; font-size: 12px; background: rgba(246,70,93,0.1); border: 1px solid var(--red); color: var(--red); }
:deep(.empty-state) { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 28px; color: var(--text-secondary); }
:deep(.empty-state .icon) { font-size: 28px; }

@media (max-width: 1200px) {
  .pnl-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 980px) {
  .status-bar { align-items: flex-start; gap: 12px; }
  .status-actions { align-items: flex-end; flex-direction: column; }
  .terminal { grid-template-columns: 1fr; }
  .account-layout { grid-template-columns: 1fr; }
  .position-panel {
    border-left: none;
    border-top: 1px solid var(--border);
    padding-left: 0;
    padding-top: 14px;
  }
  .position-list { max-height: none; }
  .pnl-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tables-row { grid-template-columns: 1fr; }
}
</style>
