<script setup>
import { ref, computed, watch, nextTick, inject, onUnmounted, onMounted } from 'vue'
import { getKline } from '../api'
import * as echarts from 'echarts'

import StateView from '../components/StateView.vue'
import { describePeriod, tfLabel } from '../utils/timeframe'
import { synthRecentTrades, synthOrderBook, normalizeToPercent } from '../utils/orderbook'

const cfg = inject('cfg')

// ---- 核心状态 ----
const symbol = ref('BTCUSDT')
const symbolSearch = ref('')
const symbolDropdownOpen = ref(false)
const timeframe = ref('1d')
const startDate = ref('')
const endDate = ref('')
const data = ref(null)
const loading = ref(false)
const error = ref('')
const fullscreen = ref(false)
const tableView = ref('chart')  // 'chart' | 'table'

// ---- 对比币种 ----
const compareSymbol = ref('')  // 空 = 不对比
const compareData = ref(null)
const compareLoading = ref(false)

// ---- 侧边栏 ----
const sideTab = ref('orderbook')  // 'orderbook' | 'trades' | 'info'

// ---- 指标配置 ----
const mainIndicators = ref({
  ma: { enabled: true, periods: [5, 10, 20, 30, 60] },
  ema: { enabled: false, periods: [12, 26] },
  boll: { enabled: false, period: 20, std: 2 },
})
const subIndicators = ref({
  volume: true,
  macd: false,
  rsi: false,
  kdj: false,
})

// MA 颜色循环
const MA_COLORS = ['#9b59b6', '#3498db', '#e67e22', '#f1c40f', '#f0b90b', '#e74c3c', '#1abc9c', '#16a085']
const COMPARE_COLOR = '#02c076'

let chart = null

// ---- 派生数据 ----
const symbolInfo = computed(() => {
  const m = {}
  for (const s of cfg.value?.symbols || []) m[s.symbol] = s
  return m
})
const timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w']
const allSymbols = computed(() => (cfg.value?.symbols || []).map(s => s.symbol))
const filteredSymbols = computed(() => {
  const t = symbolSearch.value.trim().toLowerCase()
  if (!t) return allSymbols.value.slice(0, 50)
  return allSymbols.value.filter(s =>
    s.toLowerCase().includes(t) ||
    (symbolInfo.value[s]?.name_zh || '').toLowerCase().includes(t)
  )
})
const compareOptions = computed(() => allSymbols.value.filter(s => s !== symbol.value))
const curInfo = computed(() => symbolInfo.value[symbol.value] || {})
const compareInfo = computed(() => symbolInfo.value[compareSymbol.value] || {})
const stats = computed(() => data.value?.stats || {})
const compareStats = computed(() => compareData.value?.stats || {})
const tableRows = computed(() => {
  if (!data.value?.kline) return []
  return data.value.kline.slice(-300).reverse()
})

// 当前 K 线的 OHLC (最后一根)
const lastBar = computed(() => {
  if (!data.value?.kline?.length) return null
  return data.value.kline[data.value.kline.length - 1]
})
const lastPrice = computed(() => stats.value?.last_close ?? null)
const prevClose = computed(() => {
  if (!data.value?.kline || data.value.kline.length < 2) return null
  return data.value.kline[data.value.kline.length - 2].close
})
const priceChange = computed(() => {
  if (lastPrice.value == null || prevClose.value == null) return null
  return lastPrice.value - prevClose.value
})
const priceChangePct = computed(() => {
  if (priceChange.value == null || prevClose.value === 0) return null
  return priceChange.value / prevClose.value
})
// 区间 (用户选的时间段) 的高低
const rangeHigh = computed(() => stats.value?.max_price)
const rangeLow = computed(() => stats.value?.min_price)
const rangeVol = computed(() => {
  if (!data.value?.kline) return null
  return data.value.kline.reduce((s, k) => s + (k.volume || 0), 0)
})
// 「近 24h」等价 (用 N 根近似)
// 注: 1m 1440 根, 1h 24 根, 1d 1 根
const tfMinutes = (tf) => {
  const m = { '1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440, '1w': 10080 }
  return m[tf] || 1
}
const N_PER_DAY = 1440
const recentBars = computed(() => {
  if (!data.value?.kline) return null
  const n = Math.max(1, Math.floor(N_PER_DAY / tfMinutes(timeframe.value)))
  return data.value.kline.slice(-n)
})
const high24 = computed(() => recentBars.value?.reduce((m, k) => Math.max(m, k.high), -Infinity))
const low24 = computed(() => recentBars.value?.reduce((m, k) => Math.min(m, k.low), Infinity))
const vol24 = computed(() => recentBars.value?.reduce((s, k) => s + (k.volume || 0), 0))
const open24 = computed(() => recentBars.value?.[0]?.open)
const change24 = computed(() => {
  if (lastPrice.value == null || open24.value == null) return null
  return lastPrice.value - open24.value
})
const change24Pct = computed(() => {
  if (change24.value == null || !open24.value) return null
  return change24.value / open24.value
})

// 订单簿 + 最近成交
const orderBook = computed(() => synthOrderBook(data.value?.kline, lastPrice.value, 12))
const recentTrades = computed(() => synthRecentTrades(data.value?.kline, 20))

// ---- 加载 ----
watch([symbol, timeframe], () => load(), { immediate: true })
watch([startDate, endDate], () => load())
watch([mainIndicators, subIndicators, fullscreen, tableView, compareSymbol], () => {
  if (tableView.value === 'chart') nextTick(() => drawChart())
  if (compareSymbol.value) loadCompare()
}, { deep: true })

async function load() {
  if (!startDate.value || !endDate.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await getKline(symbol.value, timeframe.value, startDate.value, endDate.value)
    if (res.data.error) {
      error.value = res.data.error
      data.value = null
    } else {
      data.value = res.data
      await nextTick()
      drawChart()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadCompare() {
  if (!compareSymbol.value || !startDate.value || !endDate.value) {
    compareData.value = null
    return
  }
  compareLoading.value = true
  try {
    const res = await getKline(compareSymbol.value, timeframe.value, startDate.value, endDate.value)
    if (!res.data.error) compareData.value = res.data
    else compareData.value = null
  } catch (e) {
    compareData.value = null
  } finally {
    compareLoading.value = false
  }
}

// ---- 工具函数: 指标计算 ----
function computeMA(closes, n) {
  if (closes.length < n) return new Array(closes.length).fill(null)
  const out = new Array(closes.length).fill(null)
  let sum = 0
  for (let i = 0; i < closes.length; i++) {
    sum += closes[i]
    if (i >= n) sum -= closes[i - n]
    if (i >= n - 1) out[i] = sum / n
  }
  return out
}
function computeEMA(closes, n) {
  if (closes.length === 0) return []
  const k = 2 / (n + 1)
  const out = new Array(closes.length).fill(null)
  let ema = closes[0]
  out[0] = ema
  for (let i = 1; i < closes.length; i++) {
    ema = closes[i] * k + ema * (1 - k)
    out[i] = ema
  }
  return out
}
function computeBOLL(closes, n = 20, k = 2) {
  const out = { upper: [], mid: [], lower: [] }
  for (let i = 0; i < closes.length; i++) {
    if (i < n - 1) { out.upper.push(null); out.mid.push(null); out.lower.push(null); continue }
    let sum = 0
    for (let j = i - n + 1; j <= i; j++) sum += closes[j]
    const mean = sum / n
    let varSum = 0
    for (let j = i - n + 1; j <= i; j++) varSum += (closes[j] - mean) ** 2
    const sd = Math.sqrt(varSum / n)
    out.mid.push(mean)
    out.upper.push(mean + k * sd)
    out.lower.push(mean - k * sd)
  }
  return out
}
function computeMACD(closes, fast = 12, slow = 26, signal = 9) {
  const emaFast = computeEMA(closes, fast)
  const emaSlow = computeEMA(closes, slow)
  const dif = emaFast.map((v, i) => v != null && emaSlow[i] != null ? v - emaSlow[i] : null)
  const validDif = dif.filter(v => v != null)
  const deaRaw = computeEMA(validDif, signal)
  const offset = dif.findIndex(v => v != null)
  const dea = new Array(dif.length).fill(null)
  for (let i = 0; i < deaRaw.length; i++) dea[offset + i] = deaRaw[i]
  const hist = dif.map((v, i) => v != null && dea[i] != null ? (v - dea[i]) * 2 : null)
  return { dif, dea, hist }
}
function computeRSI(closes, n = 14) {
  const out = new Array(closes.length).fill(null)
  if (closes.length < n + 1) return out
  let gainSum = 0, lossSum = 0
  for (let i = 1; i <= n; i++) {
    const diff = closes[i] - closes[i - 1]
    if (diff > 0) gainSum += diff; else lossSum -= diff
  }
  let avgGain = gainSum / n, avgLoss = lossSum / n
  out[n] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  for (let i = n + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1]
    const gain = diff > 0 ? diff : 0
    const loss = diff < 0 ? -diff : 0
    avgGain = (avgGain * (n - 1) + gain) / n
    avgLoss = (avgLoss * (n - 1) + loss) / n
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  }
  return out
}
function computeKDJ(closes, highs, lows, n = 9, m1 = 3, m2 = 3) {
  const k = new Array(closes.length).fill(null)
  const d = new Array(closes.length).fill(null)
  const j = new Array(closes.length).fill(null)
  let prevK = 50, prevD = 50
  for (let i = n - 1; i < closes.length; i++) {
    let lowMin = lows[i], highMax = highs[i]
    for (let j2 = i - n + 1; j2 <= i; j2++) {
      if (lows[j2] < lowMin) lowMin = lows[j2]
      if (highs[j2] > highMax) highMax = highs[j2]
    }
    const rsv = highMax === lowMin ? 0 : (closes[i] - lowMin) / (highMax - lowMin) * 100
    const curK = (m1 - 1) / m1 * prevK + 1 / m1 * rsv
    const curD = (m2 - 1) / m2 * prevD + 1 / m2 * curK
    k[i] = curK; d[i] = curD; j[i] = 3 * curK - 2 * curD
    prevK = curK; prevD = curD
  }
  return { k, d, j }
}

// ---- 绘图 ----
function getOrInitChart(elId) {
  const el = document.getElementById(elId)
  if (!el) return null
  if (!chart || chart.getDom() !== el) {
    if (chart) { try { chart.dispose() } catch (e) {} }
    chart = echarts.init(el, null, { renderer: 'canvas' })
  }
  return chart
}

function drawChart() {
  if (!data.value?.kline?.length) return
  const c = getOrInitChart('kline-chart')
  if (!c) return
  const dates = data.value.kline.map(k => k.date)
  const kline = data.value.kline
  const closes = kline.map(k => k.close)
  const highs = kline.map(k => k.high)
  const lows = kline.map(k => k.low)
  const kValues = kline.map((k) => [k.open, k.close, k.low, k.high])

  const grids = []
  const xAxes = []
  const yAxes = []
  const series = []

  const subCount = [
    subIndicators.value.volume,
    subIndicators.value.macd,
    subIndicators.value.rsi,
    subIndicators.value.kdj,
  ].filter(Boolean).length

  const MAIN_H = 70
  const SUB_H = subCount > 0 ? Math.min(15, 24 / Math.max(1, subCount)) : 0
  const GAP = 3

  // 主图
  grids.push({ left: 50, right: 70, top: 20, height: `${MAIN_H}%` })
  xAxes.push({ type: 'category', data: dates, gridIndex: 0, axisLine: { lineStyle: { color: '#2b3139' } }, axisLabel: { show: false } })
  yAxes.push({ scale: true, gridIndex: 0, position: 'right', splitLine: { lineStyle: { color: '#2b3139', type: 'dashed' } }, axisLabel: { color: '#b7bdc6', fontSize: 11 } })

  // K线
  series.push({
    name: 'K线', type: 'candlestick', data: kValues,
    xAxisIndex: 0, yAxisIndex: 0,
    itemStyle: { color: '#02c076', color0: '#f6465d', borderColor: '#02c076', borderColor0: '#f6465d' }
  })

  // 对比币种 (归一化到百分比变化)
  if (compareData.value?.kline?.length) {
    const norm = normalizeToPercent(compareData.value.kline)
    series.push({
      name: compareSymbol.value,
      type: 'line', data: norm.map(p => [p.date, p.value]),
      smooth: true, showSymbol: false,
      xAxisIndex: 0, yAxisIndex: 0,
      lineStyle: { width: 1.5, color: COMPARE_COLOR, type: 'dashed' },
      tooltip: { valueFormatter: v => v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '-' }
    })
  }

  // MA
  if (mainIndicators.value.ma.enabled) {
    mainIndicators.value.ma.periods.forEach((p, i) => {
      const ma = computeMA(closes, p)
      series.push({
        name: `MA${p}`, type: 'line', data: ma, smooth: true, showSymbol: false,
        xAxisIndex: 0, yAxisIndex: 0,
        lineStyle: { width: 1.2, color: MA_COLORS[i % MA_COLORS.length] }
      })
    })
  }
  if (mainIndicators.value.ema.enabled) {
    mainIndicators.value.ema.periods.forEach((p, i) => {
      const ema = computeEMA(closes, p)
      series.push({
        name: `EMA${p}`, type: 'line', data: ema, smooth: true, showSymbol: false,
        xAxisIndex: 0, yAxisIndex: 0,
        lineStyle: { width: 1.2, color: MA_COLORS[(i + 4) % MA_COLORS.length], type: 'dashed' }
      })
    })
  }
  if (mainIndicators.value.boll.enabled) {
    const b = computeBOLL(closes, mainIndicators.value.boll.period, mainIndicators.value.boll.std)
    series.push({ name: 'BOLL上', type: 'line', data: b.upper, smooth: true, showSymbol: false, xAxisIndex: 0, yAxisIndex: 0, lineStyle: { width: 0.8, color: '#8e44ad', opacity: 0.5 } })
    series.push({ name: 'BOLL中', type: 'line', data: b.mid, smooth: true, showSymbol: false, xAxisIndex: 0, yAxisIndex: 0, lineStyle: { width: 0.8, color: '#8e44ad', opacity: 0.7 } })
    series.push({ name: 'BOLL下', type: 'line', data: b.lower, smooth: true, showSymbol: false, xAxisIndex: 0, yAxisIndex: 0, lineStyle: { width: 0.8, color: '#8e44ad', opacity: 0.5 } })
  }

  // 副图
  let subIdx = 1
  let topPos = MAIN_H + GAP
  const subConfigs = []
  if (subIndicators.value.volume) subConfigs.push('volume')
  if (subIndicators.value.macd) subConfigs.push('macd')
  if (subIndicators.value.rsi) subConfigs.push('rsi')
  if (subIndicators.value.kdj) subConfigs.push('kdj')

  for (const sub of subConfigs) {
    grids.push({ left: 50, right: 70, top: `${topPos}%`, height: `${SUB_H}%` })
    xAxes.push({ type: 'category', data: dates, gridIndex: subIdx, axisLine: { lineStyle: { color: '#2b3139' } }, axisLabel: subIdx === subConfigs.length ? { color: '#b7bdc6', fontSize: 11 } : { show: false } })
    yAxes.push({ gridIndex: subIdx, position: 'right', splitLine: { show: false }, axisLabel: { color: '#b7bdc6', fontSize: 10 } })

    if (sub === 'volume') {
      series.push({
        name: '成交量', type: 'bar', xAxisIndex: subIdx, yAxisIndex: subIdx,
        data: kline.map((k) => ({
          value: k.volume || 0,
          itemStyle: { color: k.close >= k.open ? 'rgba(2,192,118,0.6)' : 'rgba(246,70,93,0.6)' }
        }))
      })
    } else if (sub === 'macd') {
      const m = computeMACD(closes)
      series.push({ name: 'DIF', type: 'line', data: m.dif, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx, lineStyle: { width: 1, color: '#f0b90b' } })
      series.push({ name: 'DEA', type: 'line', data: m.dea, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx, lineStyle: { width: 1, color: '#3498db' } })
      series.push({ name: 'MACD', type: 'bar', xAxisIndex: subIdx, yAxisIndex: subIdx,
        data: m.hist.map((v) => ({
          value: v == null ? 0 : v,
          itemStyle: { color: v == null ? 'transparent' : (v >= 0 ? 'rgba(2,192,118,0.7)' : 'rgba(246,70,93,0.7)') }
        })) })
    } else if (sub === 'rsi') {
      const rsi = computeRSI(closes, 14)
      series.push({ name: 'RSI', type: 'line', data: rsi, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx,
        lineStyle: { width: 1.2, color: '#f0b90b' },
        markLine: { silent: true, symbol: 'none', data: [
          { yAxis: 20, lineStyle: { color: '#f6465d', type: 'dashed' } },
          { yAxis: 80, lineStyle: { color: '#02c076', type: 'dashed' } },
        ] } })
    } else if (sub === 'kdj') {
      const kdj = computeKDJ(closes, highs, lows)
      series.push({ name: 'K', type: 'line', data: kdj.k, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx, lineStyle: { width: 1, color: '#f0b90b' } })
      series.push({ name: 'D', type: 'line', data: kdj.d, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx, lineStyle: { width: 1, color: '#3498db' } })
      series.push({ name: 'J', type: 'line', data: kdj.j, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx, lineStyle: { width: 1, color: '#9b59b6' } })
    }
    subIdx++
    topPos += SUB_H + GAP
  }

  const dataZoom = [
    { type: 'inside', xAxisIndex: grids.map((_, i) => i) },
    { type: 'slider', xAxisIndex: grids.map((_, i) => i), height: 20, bottom: 8, backgroundColor: '#181a20' }
  ]

  // 标记线: 最近价水平线
  const markLine = lastPrice.value != null ? {
    silent: true, symbol: 'none',
    data: [{ yAxis: lastPrice.value, lineStyle: { color: '#f0b90b', type: 'dashed', width: 0.8 }, label: { show: false } }],
  } : undefined

  const option = {
    backgroundColor: 'transparent',
    animation: false,
    title: {
      text: compareSymbol.value
        ? `${symbol.value} (实价) vs ${compareSymbol.value} (%变化)`
        : `${symbol.value} · ${tfLabel(timeframe.value)}`,
      left: 8, top: 6, textStyle: { color: '#b7bdc6', fontSize: 12, fontWeight: 'normal' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }] },
      backgroundColor: 'rgba(24,26,32,0.95)',
      borderColor: '#474d57',
      textStyle: { color: '#eaecef', fontSize: 12 },
      formatter: (params) => {
        if (!params || !params.length) return ''
        const candle = params.find(p => p.seriesType === 'candlestick')
        if (!candle) {
          return params.map(p => {
            const v = typeof p.value === 'number' ? p.value.toFixed(2) : p.value
            return `${p.marker} ${p.seriesName}: <b>${v}</b>`
          }).join('<br/>') + `<br/><span style="color:#888">${params[0].axisValueLabel}</span>`
        }
        const d = candle.data || []
        const o = d[0], c = d[1], l = d[2], h = d[3]
        if (o == null || c == null) return ''
        const chg = c - o
        const chgPct = o ? (chg / o * 100).toFixed(2) : '0.00'
        const color = chg >= 0 ? '#02c076' : '#f6465d'
        let html = `<div style="font-weight:600;margin-bottom:4px">${candle.axisValueLabel}</div>`
        html += `<table style="font-family:Consolas,monospace;font-size:12px">`
        html += `<tr><td>开</td><td style="text-align:right"><b>${(+o).toFixed(2)}</b></td></tr>`
        html += `<tr><td>收</td><td style="text-align:right;color:${color}"><b>${(+c).toFixed(2)} (${chg >= 0 ? '+' : ''}${chgPct}%)</b></td></tr>`
        html += `<tr><td>高</td><td style="text-align:right;color:#02c076">${(+h).toFixed(2)}</td></tr>`
        html += `<tr><td>低</td><td style="text-align:right;color:#f6465d">${(+l).toFixed(2)}</td></tr>`
        for (const p of params) {
          if (p.seriesType === 'candlestick') continue
          if (p.value == null || p.value === '') continue
          const v = typeof p.value === 'number' ? p.value.toFixed(4) : p.value
          html += `<tr><td>${p.marker} ${p.seriesName}</td><td style="text-align:right"><b>${v}</b></td></tr>`
        }
        html += `</table>`
        return html
      }
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes.map((y, i) => i === 0 && markLine ? { ...y, markLine } : y),
    series,
    dataZoom,
  }
  try {
    c.setOption(option, true)
  } catch (e) {
    console.error('[KLine] setOption error:', e)
  }
}

// ---- 交互 ----
function onResize() { chart?.resize() }
window.addEventListener('resize', onResize)
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  if (chart) { try { chart.dispose() } catch (e) {} }
})

function pickSymbol(s) {
  symbol.value = s
  symbolDropdownOpen.value = false
  symbolSearch.value = ''
}
function toggleFullscreen() { fullscreen.value = !fullscreen.value }

function fmt(v, d = 2) {
  if (v === null || v === undefined) return '-'
  if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(2) + 'K'
  return Number(v).toFixed(d)
}
function fmtBig(v) {
  if (!v) return '-'
  if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(2) + 'K'
  return v.toFixed(0)
}
function fmtPrice(p, base) {
  if (p == null) return '-'
  const d = base < 1 ? 6 : base < 10 ? 4 : base < 100 ? 3 : 2
  return p.toFixed(d)
}
function fmtTime(s) {
  if (!s) return ''
  // 兼容 2025-06-21 / 20250601 两种格式
  if (s.length === 10 && s.includes('-')) return s.slice(5)  // 2025-06-21 -> 06-21
  if (s.length === 8) return `${s.slice(4, 6)}-${s.slice(6, 8)}`  // 20250601 -> 06-01
  return s
}

// 快捷日期预设
const datePresets = [
  { id: '1w', label: '1周', days: 7 },
  { id: '1m', label: '1月', days: 30 },
  { id: '3m', label: '3月', days: 90 },
  { id: '6m', label: '6月', days: 180 },
  { id: '1y', label: '1年', days: 365 },
  { id: '2y', label: '2年', days: 730 },
  { id: 'all', label: '全部', days: null },
]
const activeDatePreset = ref('')
function setDatePreset(p) {
  activeDatePreset.value = p.id
  const now = new Date()
  let start
  if (p.days) {
    const d = new Date(now)
    d.setDate(d.getDate() - p.days)
    start = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
  } else {
    start = '20170101'
  }
  const end = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
  startDate.value = start
  endDate.value = end
  if (p.id !== '__smart' && p.id !== '__init') autoRangeDisabled.value = true
}

watch([startDate, endDate], () => {
  const now = new Date()
  const todayStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
  if (endDate.value !== todayStr) { activeDatePreset.value = ''; return }
  for (const p of datePresets) {
    if (!p.days) continue
    const d = new Date(now)
    d.setDate(d.getDate() - p.days)
    const startStr = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
    if (startStr === startDate.value) { activeDatePreset.value = p.id; return }
  }
  activeDatePreset.value = ''
})

// 智能选默认
const autoRangeDisabled = ref(false)
function applySmartDefault() {
  if (autoRangeDisabled.value) return
  const tf = timeframe.value
  const smartDays = { '1m': 7, '5m': 14, '15m': 30, '30m': 60, '1h': 90, '4h': 180, '1d': 365, '1w': 730 }
  const days = smartDays[tf] || 90
  setDatePreset({ id: '__smart', label: '', days })
}
onMounted(() => { if (!startDate.value || !endDate.value) applySmartDefault() })
watch(timeframe, () => applySmartDefault())
</script>

<template>
  <div class="kline-binance" :class="{ fullscreen }">
    <!-- 顶部: 币种 + 实时报价 (Binance 风格) -->
    <div class="quote-header">
      <div class="symbol-section">
        <div class="symbol-dropdown" :class="{ open: symbolDropdownOpen }">
          <button class="symbol-trigger" @click="symbolDropdownOpen = !symbolDropdownOpen">
            <div class="sym-info">
              <span class="sym-name">{{ curInfo.name_zh || symbol }}</span>
              <span class="sym-pair">/{{ symbol }}</span>
            </div>
            <span class="dropdown-arrow">▾</span>
          </button>
          <transition name="dropdown">
            <div v-if="symbolDropdownOpen" class="symbol-panel" @click.self="symbolDropdownOpen = false">
              <div class="symbol-search-bar">
                <input v-model="symbolSearch" placeholder="🔍 搜索币种 / 中文名..." autofocus />
                <span class="search-hint">共 {{ allSymbols.length }} 个</span>
              </div>
              <div class="symbol-list">
                <button v-for="s in filteredSymbols" :key="s"
                  :class="{ active: s === symbol }"
                  @click="pickSymbol(s)">
                  <span class="sym-icon">{{ symbolInfo[s]?.name_zh?.charAt(0) || '?' }}</span>
                  <div class="sym-row">
                    <span class="sym-code">{{ s }}</span>
                    <span class="sym-zh">{{ symbolInfo[s]?.name_zh || '—' }}</span>
                  </div>
                  <span v-if="symbolInfo[s]?.category" class="sym-cat">{{ symbolInfo[s].category }}</span>
                </button>
                <div v-if="!filteredSymbols.length" class="empty">未找到币种</div>
              </div>
            </div>
          </transition>
        </div>
        <div class="price-block">
          <div class="price-main" :class="priceChange >= 0 ? 'pos' : 'neg'">
            {{ lastPrice != null ? lastPrice.toFixed(lastPrice < 1 ? 4 : 2) : '—' }}
          </div>
          <div class="price-sub">
            <span class="chg-abs" :class="priceChange >= 0 ? 'pos' : 'neg'">
              {{ priceChange != null ? (priceChange >= 0 ? '+' : '') + priceChange.toFixed(2) : '—' }}
            </span>
            <span class="chg-pct" :class="priceChangePct >= 0 ? 'pos' : 'neg'">
              {{ priceChangePct != null ? (priceChangePct >= 0 ? '+' : '') + (priceChangePct * 100).toFixed(2) + '%' : '—' }}
            </span>
          </div>
        </div>
      </div>
      <div class="header-actions">
        <button class="icon-btn" :class="{ active: fullscreen }" @click="toggleFullscreen" :title="fullscreen ? '退出全屏' : '全屏'">⛶</button>
        <button class="icon-btn" @click="load" :disabled="loading" title="刷新数据">🔄</button>
      </div>
    </div>

    <!-- 时间框架 + 日期 (紧凑单行) -->
    <div class="toolbar-row">
      <div class="tf-tabs">
        <button v-for="tf in timeframes" :key="tf"
          :class="{ active: tf === timeframe }"
          @click="timeframe = tf"
          :title="tfLabel(tf)">
          {{ tf }}
        </button>
      </div>
      <div class="date-presets">
        <button v-for="p in datePresets.filter(x => x.id !== 'all')" :key="p.id"
          :class="{ active: activeDatePreset === p.id }"
          @click="setDatePreset(p)">
          {{ p.label }}
        </button>
        <span class="date-range-label">{{ fmtTime(startDate) || '?' }} → {{ fmtTime(endDate) || '?' }}</span>
      </div>
    </div>

    <!-- 指标工具栏 (主图 + 副图分别配置) -->
    <div class="indicator-bar">
      <div class="ib-group">
        <span class="ib-lbl">主图</span>
        <label class="ib-toggle" :class="{ on: mainIndicators.ma.enabled }">
          <input type="checkbox" v-model="mainIndicators.ma.enabled" />
          <span>MA</span>
        </label>
        <div v-if="mainIndicators.ma.enabled" class="ma-periods">
          <label v-for="p in [5, 10, 20, 30, 60, 120]" :key="p" class="period-chip" :class="{ on: mainIndicators.ma.periods.includes(p) }">
            <input type="checkbox" :value="p" v-model="mainIndicators.ma.periods" />
            <span>{{ p }}</span>
          </label>
          <span class="period-hint">~{{ describePeriod(7, timeframe) }}示例</span>
        </div>
        <label class="ib-toggle" :class="{ on: mainIndicators.ema.enabled }">
          <input type="checkbox" v-model="mainIndicators.ema.enabled" />
          <span>EMA</span>
        </label>
        <label class="ib-toggle" :class="{ on: mainIndicators.boll.enabled }">
          <input type="checkbox" v-model="mainIndicators.boll.enabled" />
          <span>BOLL</span>
        </label>
      </div>
      <div class="ib-sep">|</div>
      <div class="ib-group">
        <span class="ib-lbl">副图</span>
        <label class="ib-toggle" :class="{ on: subIndicators.volume }">
          <input type="checkbox" v-model="subIndicators.volume" />
          <span>成交量</span>
        </label>
        <label class="ib-toggle" :class="{ on: subIndicators.macd }">
          <input type="checkbox" v-model="subIndicators.macd" />
          <span>MACD</span>
        </label>
        <label class="ib-toggle" :class="{ on: subIndicators.rsi }">
          <input type="checkbox" v-model="subIndicators.rsi" />
          <span>RSI</span>
        </label>
        <label class="ib-toggle" :class="{ on: subIndicators.kdj }">
          <input type="checkbox" v-model="subIndicators.kdj" />
          <span>KDJ</span>
        </label>
      </div>
      <div class="ib-sep">|</div>
      <div class="ib-group">
        <span class="ib-lbl">对比</span>
        <select v-model="compareSymbol" class="compare-select">
          <option value="">无</option>
          <option v-for="s in compareOptions" :key="s" :value="s">{{ s }}</option>
        </select>
      </div>
      <div class="ib-sep">|</div>
      <div class="ib-group">
        <button :class="{ active: tableView === 'chart' }" @click="tableView = 'chart'">📈 图表</button>
        <button :class="{ active: tableView === 'table' }" @click="tableView = 'table'">📋 数据</button>
      </div>
    </div>

    <!-- 主内容区: 图表 + 侧边栏 -->
    <div class="main-content">
      <!-- 图表区 -->
      <div class="chart-column">
        <div v-if="tableView === 'chart'" class="chart-area">
          <!-- OHLC 紧凑信息条 (左上角, Binance 风格) -->
          <div v-if="lastBar" class="ohlc-strip">
            <span class="oh-item"><span class="oh-lbl">开</span><span class="oh-val">{{ fmtPrice(lastBar.open, lastPrice) }}</span></span>
            <span class="oh-item"><span class="oh-lbl">高</span><span class="oh-val pos">{{ fmtPrice(lastBar.high, lastPrice) }}</span></span>
            <span class="oh-item"><span class="oh-lbl">低</span><span class="oh-val neg">{{ fmtPrice(lastBar.low, lastPrice) }}</span></span>
            <span class="oh-item"><span class="oh-lbl">收</span><span class="oh-val" :class="lastBar.close >= lastBar.open ? 'pos' : 'neg'">{{ fmtPrice(lastBar.close, lastPrice) }}</span></span>
            <span class="oh-sep"></span>
            <span class="oh-item"><span class="oh-lbl">24h 涨跌</span><span class="oh-val" :class="change24Pct >= 0 ? 'pos' : 'neg'">{{ change24Pct != null ? (change24Pct >= 0 ? '+' : '') + (change24Pct * 100).toFixed(2) + '%' : '—' }}</span></span>
            <span class="oh-item"><span class="oh-lbl">24h 高</span><span class="oh-val pos">{{ high24 != null ? fmtPrice(high24, lastPrice) : '—' }}</span></span>
            <span class="oh-item"><span class="oh-lbl">24h 低</span><span class="oh-val neg">{{ low24 != null ? fmtPrice(low24, lastPrice) : '—' }}</span></span>
            <span class="oh-item"><span class="oh-lbl">24h 量</span><span class="oh-val">{{ fmtBig(vol24) }}</span></span>
            <span class="oh-sep"></span>
            <span class="oh-item" v-if="compareSymbol">
              <span class="oh-lbl">对比</span>
              <span class="oh-val" style="color:#02c076">{{ compareSymbol }} (绿虚线, %变化)</span>
            </span>
          </div>
          <div v-if="loading && !data" class="loading-state">
            <div class="spinner"></div>
            <span>正在获取 {{ symbol }} {{ timeframe }} K线数据...</span>
          </div>
          <div v-else-if="!data?.kline?.length && !loading" class="empty-state">
            <div class="icon">📊</div>
            <div>选择币种和周期, 加载 K线数据</div>
          </div>
          <div v-show="data?.kline?.length" id="kline-chart" class="chart"></div>
          <div v-if="loading && data" class="loading-overlay">
            <div class="spinner small"></div>
          </div>
        </div>

        <!-- 数据表 -->
        <div v-else class="table-area">
          <div class="table-toolbar">
            <span class="table-hint">显示最近 {{ tableRows.length }} 条 (共 {{ stats.rows || 0 }} 条)</span>
            <button class="icon-btn" @click="tableView = 'chart'">📈 切回图表</button>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>时间</th><th>开</th><th>高</th><th>低</th><th>收</th>
                  <th>涨跌%</th><th>成交量</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in tableRows" :key="r.date">
                  <td>{{ r.date }}</td>
                  <td>{{ fmt(r.open) }}</td>
                  <td class="pos">{{ fmt(r.high) }}</td>
                  <td class="neg">{{ fmt(r.low) }}</td>
                  <td :class="r.close > r.open ? 'pos' : 'neg'">{{ fmt(r.close) }}</td>
                  <td :class="r.close >= r.open ? 'pos' : 'neg'">
                    {{ r.open ? ((r.close - r.open) / r.open * 100).toFixed(2) : '-' }}%
                  </td>
                  <td>{{ fmtBig(r.volume) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- 侧边栏: 订单簿 / 最近成交 / 币种信息 -->
      <div class="side-panel">
        <div class="side-tabs">
          <button :class="{ active: sideTab === 'orderbook' }" @click="sideTab = 'orderbook'">📊 订单簿</button>
          <button :class="{ active: sideTab === 'trades' }" @click="sideTab = 'trades'">💱 成交</button>
          <button :class="{ active: sideTab === 'info' }" @click="sideTab = 'info'">ℹ️ 信息</button>
        </div>

        <!-- 订单簿 -->
        <div v-if="sideTab === 'orderbook'" class="orderbook">
          <div class="ob-head">
            <span>价格 ({{ symbol }})</span>
            <span>数量</span>
            <span>累计</span>
          </div>
          <!-- 卖盘 (asks, 从高到低) -->
          <div class="ob-asks">
            <div v-for="(row, i) in orderBook.asks.slice().reverse()" :key="`a${i}`" class="ob-row ask">
              <span class="ob-price">{{ fmtPrice(row.price, lastPrice) }}</span>
              <span class="ob-amount">{{ fmt(row.amount, 0) }}</span>
              <span class="ob-total">{{ fmt(row.total, 0) }}</span>
              <span class="ob-bar" :style="{ width: Math.min(100, row.total / Math.max(...orderBook.asks.map(a => a.total), ...orderBook.bids.map(b => b.total), 1) * 100) + '%' }"></span>
            </div>
          </div>
          <!-- 当前价 -->
          <div class="ob-mid" :class="priceChange >= 0 ? 'pos' : 'neg'">
            {{ fmtPrice(lastPrice, lastPrice) }}
            <span class="ob-mid-sub">≈ 实时 (基于 K 线收盘)</span>
          </div>
          <!-- 买盘 (bids, 从高到低) -->
          <div class="ob-bids">
            <div v-for="(row, i) in orderBook.bids" :key="`b${i}`" class="ob-row bid">
              <span class="ob-price">{{ fmtPrice(row.price, lastPrice) }}</span>
              <span class="ob-amount">{{ fmt(row.amount, 0) }}</span>
              <span class="ob-total">{{ fmt(row.total, 0) }}</span>
              <span class="ob-bar" :style="{ width: Math.min(100, row.total / Math.max(...orderBook.bids.map(b => b.total), ...orderBook.asks.map(a => a.total), 1) * 100) + '%' }"></span>
            </div>
          </div>
          <div class="ob-hint">⚠ 订单簿为基于历史 K 线的合成深度, 非真实盘口</div>
        </div>

        <!-- 最近成交 -->
        <div v-if="sideTab === 'trades'" class="trades">
          <div class="trades-head">
            <span>时间</span>
            <span>价格</span>
            <span>数量</span>
          </div>
          <div class="trades-list">
            <div v-for="(t, i) in recentTrades" :key="i" class="trade-row" :class="t.side">
              <span class="t-time">{{ fmtTime(t.time) }}</span>
              <span class="t-price">{{ fmtPrice(t.price, lastPrice) }}</span>
              <span class="t-amount">{{ fmt(t.amount, 0) }}</span>
            </div>
            <div v-if="!recentTrades.length" class="empty">暂无成交</div>
          </div>
        </div>

        <!-- 币种信息 -->
        <div v-if="sideTab === 'info'" class="info">
          <div v-if="curInfo.symbol" class="info-section">
            <h4>{{ curInfo.name_zh }} <span class="muted">({{ curInfo.name_en }})</span></h4>
            <div class="info-row"><span class="ir-lbl">代码</span><span class="ir-val mono">{{ curInfo.symbol }}</span></div>
            <div class="info-row"><span class="ir-lbl">分类</span><span class="ir-val">{{ curInfo.category }}</span></div>
            <div class="info-row" v-if="curInfo.market_cap_rank"><span class="ir-lbl">市值排名</span><span class="ir-val">#{{ curInfo.market_cap_rank }}</span></div>
            <div class="info-row" v-if="curInfo.tags?.length">
              <span class="ir-lbl">标签</span>
              <span class="ir-val tags">
                <span v-for="t in curInfo.tags" :key="t" class="tag">#{{ t }}</span>
              </span>
            </div>
            <p v-if="curInfo.description" class="info-desc">{{ curInfo.description }}</p>
          </div>
          <div v-if="compareSymbol && compareInfo.symbol" class="info-section">
            <h4>对比: {{ compareInfo.name_zh }} <span class="muted">({{ compareInfo.name_en }})</span></h4>
            <div class="info-row"><span class="ir-lbl">代码</span><span class="ir-val mono">{{ compareInfo.symbol }}</span></div>
            <div class="info-row"><span class="ir-lbl">分类</span><span class="ir-val">{{ compareInfo.category }}</span></div>
            <p class="info-desc">绿虚线为 {{ compareSymbol }} 的累计涨跌幅 (起点 0%), 跟主图 {{ symbol }} 实价对比</p>
          </div>
        </div>
      </div>
    </div>

    <StateView :error="error" v-if="!loading && error" />
  </div>
</template>

<style scoped>
.kline-binance { display: flex; flex-direction: column; gap: 12px; }
.kline-binance.fullscreen {
  position: fixed; inset: 0; z-index: 999;
  background: var(--bg);
  padding: 16px;
  overflow: auto;
}

/* 顶部报价区 */
.quote-header {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}
.symbol-section { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.symbol-dropdown { position: relative; }
.symbol-trigger {
  background: transparent;
  border: 0;
  color: var(--text);
  padding: 4px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.sym-info { display: flex; align-items: baseline; gap: 4px; }
.sym-name { font-size: 20px; font-weight: 700; color: var(--text); }
.sym-pair { font-size: 14px; color: var(--text-secondary); }
.dropdown-arrow { color: var(--text-muted); font-size: 14px; }
.symbol-trigger:hover .sym-name { color: var(--yellow); }
.symbol-panel {
  position: absolute; top: 100%; left: 0; z-index: 100;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  width: 360px;
  max-height: 480px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  margin-top: 4px;
}
.symbol-search-bar {
  display: flex; align-items: center; gap: 8px;
  padding-bottom: 8px; border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}
.symbol-search-bar input {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
  outline: none;
}
.symbol-search-bar input:focus { border-color: var(--yellow); }
.search-hint { font-size: 10px; color: var(--text-muted); }
.symbol-list { max-height: 360px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.symbol-list button {
  display: flex; align-items: center; gap: 10px;
  background: transparent;
  border: 0;
  color: var(--text);
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  text-align: left;
  font-size: 13px;
}
.symbol-list button:hover { background: var(--bg-elevated); }
.symbol-list button.active { background: rgba(240,185,11,0.15); color: var(--yellow); }
.sym-icon {
  width: 24px; height: 24px;
  background: var(--bg-elevated);
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600;
  color: var(--text-secondary);
}
.sym-row { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.sym-code { font-size: 13px; font-weight: 600; font-family: 'Consolas', monospace; }
.sym-zh { font-size: 10px; color: var(--text-muted); }
.sym-cat { font-size: 9px; background: var(--bg-elevated); color: var(--text-muted); padding: 1px 6px; border-radius: 8px; }
.empty { padding: 30px; text-align: center; color: var(--text-muted); font-size: 12px; }

.price-block { display: flex; flex-direction: column; gap: 2px; }
.price-main { font-size: 28px; font-weight: 700; font-family: 'Consolas', monospace; line-height: 1.1; }
.price-main.pos { color: var(--green); }
.price-main.neg { color: var(--red); }
.price-sub { display: flex; gap: 8px; font-size: 13px; font-family: 'Consolas', monospace; }
.chg-abs.pos, .chg-pct.pos { color: var(--green); }
.chg-abs.neg, .chg-pct.neg { color: var(--red); }

.header-actions { display: flex; gap: 6px; }
.icon-btn {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}
.icon-btn:hover { border-color: var(--yellow); color: var(--yellow); }
.icon-btn.active { background: rgba(240,185,11,0.1); border-color: var(--yellow); color: var(--yellow); }
.icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* 时间框架 + 日期工具栏 */
.toolbar-row {
  display: flex;
  align-items: center;
  gap: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 14px;
  flex-wrap: wrap;
}
.tf-tabs { display: flex; gap: 2px; }
.tf-tabs button {
  background: transparent;
  color: var(--text-secondary);
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  font-weight: 600;
  border: 0;
  cursor: pointer;
}
.tf-tabs button:hover { background: var(--bg-elevated); }
.tf-tabs button.active { background: var(--yellow); color: #000; }
.date-presets { display: flex; gap: 2px; align-items: center; flex-wrap: wrap; }
.date-presets button {
  background: transparent;
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  border: 0;
  cursor: pointer;
}
.date-presets button:hover { background: var(--bg-elevated); }
.date-presets button.active { background: rgba(240,185,11,0.15); color: var(--yellow); }
.date-range-label { margin-left: auto; font-size: 11px; color: var(--text-muted); font-family: 'Consolas', monospace; }

/* 指标工具栏 */
.indicator-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 14px;
  flex-wrap: wrap;
  font-size: 12px;
}
.ib-group { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.ib-lbl { color: var(--text-muted); font-weight: 600; margin-right: 2px; }
.ib-toggle {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px;
  border-radius: 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  cursor: pointer;
  user-select: none;
  color: var(--text-secondary);
}
.ib-toggle input { margin: 0; accent-color: var(--yellow); }
.ib-toggle.on { background: rgba(240,185,11,0.15); border-color: var(--yellow); color: var(--yellow); }
.ma-periods { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.period-chip {
  display: inline-flex; align-items: center;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  cursor: pointer;
  font-size: 11px;
  font-family: 'Consolas', monospace;
  color: var(--text-secondary);
}
.period-chip input { display: none; }
.period-chip.on { background: var(--yellow); color: #000; border-color: var(--yellow); }
.period-hint { color: var(--text-muted); font-size: 10px; margin-left: 4px; }
.ib-sep { color: var(--border); }
.indicator-bar button {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}
.indicator-bar button.active { background: rgba(240,185,11,0.15); border-color: var(--yellow); color: var(--yellow); }
.compare-select {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  outline: none;
  cursor: pointer;
}
.compare-select:focus { border-color: var(--yellow); }

/* 主内容区: 左图表 + 右侧边栏 */
.main-content {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 12px;
}
@media (max-width: 1200px) {
  .main-content { grid-template-columns: 1fr; }
}

/* 主图区 */
.chart-column { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.chart-area {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  min-height: 580px;
}
.chart { height: 600px; }
.fullscreen .chart-area { height: calc(100vh - 240px); display: flex; flex-direction: column; }
.fullscreen .chart { flex: 1; min-height: 400px; }

/* OHLC 紧凑信息条 (Binance 风格: 图表顶部一行) */
.ohlc-strip {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 6px 4px 8px 4px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
  font-size: 12px;
  flex-wrap: wrap;
}
.oh-item { display: inline-flex; gap: 4px; align-items: baseline; }
.oh-lbl { color: var(--text-muted); font-size: 10px; }
.oh-val { font-family: 'Consolas', monospace; font-weight: 600; }
.oh-val.pos { color: var(--green); }
.oh-val.neg { color: var(--red); }
.oh-sep { width: 1px; height: 14px; background: var(--border); }

.loading-state {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 16px;
  color: var(--text-secondary);
  font-size: 13px;
}
.empty-state {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px;
  color: var(--text-muted);
}
.empty-state .icon { font-size: 48px; }
.loading-overlay {
  position: absolute; top: 16px; right: 16px;
  background: rgba(24,26,32,0.9);
  border: 1px solid var(--border);
  border-radius: 50%;
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
}
.spinner {
  width: 40px; height: 40px;
  border: 3px solid var(--border);
  border-top-color: var(--yellow);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.spinner.small { width: 20px; height: 20px; border-width: 2px; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 数据表 */
.table-area {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
}
.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.table-hint { font-size: 12px; color: var(--text-muted); }
.table-wrap { max-height: 600px; overflow: auto; }
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left;
  padding: 8px 10px;
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  border-bottom: 1px solid var(--border);
  position: sticky; top: 0;
}
td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  font-family: 'Consolas', monospace;
}
tr:hover td { background: var(--bg-elevated); }
.pos { color: var(--green); }
.neg { color: var(--red); }

/* 侧边栏 */
.side-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  min-width: 0;
  max-height: 700px;
}
.side-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  padding: 0 8px;
}
.side-tabs button {
  background: transparent;
  border: 0;
  color: var(--text-secondary);
  padding: 10px 12px;
  font-size: 12px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.side-tabs button:hover { color: var(--text); }
.side-tabs button.active { color: var(--yellow); border-bottom-color: var(--yellow); }

/* 订单簿 */
.orderbook { padding: 8px; font-family: 'Consolas', monospace; font-size: 11px; overflow: auto; }
.ob-head, .trade-row, .trades-head {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  gap: 6px;
  padding: 4px 6px;
  color: var(--text-muted);
  font-size: 10px;
}
.ob-row {
  position: relative;
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  gap: 6px;
  padding: 3px 6px;
  font-family: 'Consolas', monospace;
  font-size: 11px;
  border-radius: 2px;
}
.ob-row:hover { background: var(--bg-elevated); }
.ob-row.ask .ob-price { color: var(--red); }
.ob-row.bid .ob-price { color: var(--green); }
.ob-amount, .ob-total { text-align: right; color: var(--text-secondary); }
.ob-bar {
  position: absolute;
  top: 0; right: 0; bottom: 0;
  pointer-events: none;
  border-radius: 2px;
}
.ob-row.ask .ob-bar { background: rgba(246,70,93,0.10); }
.ob-row.bid .ob-bar { background: rgba(2,192,118,0.10); }
.ob-mid {
  text-align: center;
  padding: 8px;
  font-size: 16px;
  font-weight: 700;
  font-family: 'Consolas', monospace;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  position: relative;
}
.ob-mid.pos { color: var(--green); }
.ob-mid.neg { color: var(--red); }
.ob-mid-sub { display: block; font-size: 9px; font-weight: 400; color: var(--text-muted); margin-top: 2px; }
.ob-hint { padding: 6px 8px; font-size: 10px; color: var(--text-muted); text-align: center; }

/* 最近成交 */
.trades { padding: 8px; overflow: auto; }
.trades-list { display: flex; flex-direction: column; }
.trade-row { padding: 3px 6px; border-radius: 2px; }
.trade-row:hover { background: var(--bg-elevated); }
.trade-row.buy .t-price { color: var(--green); }
.trade-row.sell .t-price { color: var(--red); }
.t-time { color: var(--text-muted); }
.t-amount { text-align: right; color: var(--text-secondary); }

/* 币种信息 */
.info { padding: 16px; overflow: auto; font-size: 13px; }
.info-section { margin-bottom: 20px; }
.info-section h4 { font-size: 14px; margin-bottom: 8px; color: var(--yellow); }
.muted { color: var(--text-muted); font-size: 12px; }
.info-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.ir-lbl { color: var(--text-muted); }
.ir-val { color: var(--text); }
.ir-val.mono { font-family: 'Consolas', monospace; }
.tags { display: flex; flex-wrap: wrap; gap: 4px; }
.tag {
  background: var(--bg-elevated);
  color: var(--text-secondary);
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 10px;
}
.info-desc {
  margin-top: 8px;
  color: var(--text-secondary);
  line-height: 1.6;
  font-size: 12px;
}

.dropdown-enter-active, .dropdown-leave-active { transition: opacity 0.15s, transform 0.15s; }
.dropdown-enter-from, .dropdown-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
