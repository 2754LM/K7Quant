<script setup>
import { ref, computed, watch, nextTick, inject, onUnmounted, onMounted } from 'vue'
import { getKline } from '../api'
import * as echarts from 'echarts'

import StateView from '../components/StateView.vue'
import { describePeriod, tfLabel } from '../utils/timeframe'

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

// ---- 指标配置 ----
const mainIndicators = ref({
  ma: { enabled: true, periods: [5, 10, 20, 30, 60] },
  ema: { enabled: false, periods: [12, 26] },
  boll: { enabled: false, period: 20, std: 2 },
})
const subIndicators = ref({
  volume: true,
  macd: false,    // MACD 在副图
  rsi: false,     // RSI 在副图
  kdj: false,
})

// MA 颜色循环
const MA_COLORS = ['#9b59b6', '#3498db', '#e67e22', '#f1c40f', '#f0b90b', '#e74c3c', '#1abc9c', '#16a085']

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
const curInfo = computed(() => symbolInfo.value[symbol.value] || {})
const stats = computed(() => data.value?.stats || {})
const tableRows = computed(() => {
  if (!data.value?.kline) return []
  return data.value.kline.slice(-300).reverse()
})
// 实时价格 (最后一根 K 线收盘)
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
const high24 = computed(() => stats.value?.max_price)
const low24 = computed(() => stats.value?.min_price)
const vol24 = computed(() => {
  if (!data.value?.kline) return null
  const last = data.value.kline.slice(-Math.max(1, Math.floor(1440 / tfMinutes(timeframe.value))))
  return last.reduce((s, k) => s + (k.volume || 0), 0)
})

// ---- 加载 ----
watch([symbol, timeframe], () => load(), { immediate: true })
watch([startDate, endDate], () => load())
watch([mainIndicators, subIndicators, fullscreen, tableView], () => {
  if (tableView.value === 'chart') nextTick(() => drawChart())
}, { deep: true })

function tfMinutes(tf) {
  const m = { '1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440, '1w': 10080 }
  return m[tf] || 1
}

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
  // 把 dea 对齐回 dif 的下标
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

  // ---- 主图: K线 + 主指标 (MA/EMA/BOLL) ----
  const grids = []
  const xAxes = []
  const yAxes = []
  const series = []

  // 计算需要几个副图
  const subCount = [
    subIndicators.value.volume,
    subIndicators.value.macd,
    subIndicators.value.rsi,
    subIndicators.value.kdj,
  ].filter(Boolean).length

  const TOTAL_H = 80  // 主图占比 %
  const SUB_H = subCount > 0 ? Math.min(15, 60 / subCount) : 0
  const GAP = 2

  // 主图网格
  grids.push({ left: 60, right: 70, top: 30, height: `${TOTAL_H}%` })
  xAxes.push({ type: 'category', data: dates, gridIndex: 0, axisLine: { lineStyle: { color: '#2b3139' } }, axisLabel: { show: false } })
  yAxes.push({ scale: true, gridIndex: 0, position: 'right', splitLine: { lineStyle: { color: '#2b3139', type: 'dashed' } }, axisLabel: { color: '#b7bdc6', fontSize: 11 } })

  // K线
  series.push({
    name: 'K线', type: 'candlestick', data: kValues,
    xAxisIndex: 0, yAxisIndex: 0,
    itemStyle: { color: '#02c076', color0: '#f6465d', borderColor: '#02c076', borderColor0: '#f6465d' }
  })

  // MA 叠加
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

  // ---- 副图: 成交量 / MACD / RSI / KDJ ----
  let subIdx = 1
  let topPos = TOTAL_H + GAP
  const subConfigs = []
  if (subIndicators.value.volume) subConfigs.push('volume')
  if (subIndicators.value.macd) subConfigs.push('macd')
  if (subIndicators.value.rsi) subConfigs.push('rsi')
  if (subIndicators.value.kdj) subConfigs.push('kdj')

  for (const sub of subConfigs) {
    grids.push({ left: 60, right: 70, top: `${topPos}%`, height: `${SUB_H}%` })
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

  // dataZoom
  const dataZoom = [
    { type: 'inside', xAxisIndex: grids.map((_, i) => i) },
    { type: 'slider', xAxisIndex: grids.map((_, i) => i), height: 20, bottom: 8, backgroundColor: '#181a20' }
  ]

  const option = {
    backgroundColor: 'transparent',
    animation: false,
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
          // 副图 tooltip
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
    yAxis: yAxes,
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
function toggleFullscreen() {
  fullscreen.value = !fullscreen.value
}

function fmt(v, d = 2) {
  if (v === null || v === undefined) return '-'
  if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(2) + 'K'
  return Number(v).toFixed(d)
}
function fmtPct(v) { return v === null || v === undefined ? '-' : (v * 100).toFixed(2) + '%' }
function fmtBig(v) {  // 成交量格式化
  if (!v) return '-'
  if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(2) + 'K'
  return v.toFixed(0)
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
  // 标记: 用户主动选过预设, 后续切换 tf 不再自动覆盖
  if (p.id !== '__smart' && p.id !== '__init') autoRangeDisabled.value = true
}
watch([startDate, endDate], () => {
  // 检查当前是否匹配某个 preset
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

// 初始化 + timeframe 切换时: 智能选默认区间 (避免拖慢首屏)
function applySmartDefault() {
  if (autoRangeDisabled.value) return  // 用户手动选过日期后, 不再自动改
  const tf = timeframe.value
  const smartDays = { '1m': 7, '5m': 14, '15m': 30, '30m': 60, '1h': 90, '4h': 180, '1d': 365, '1w': 730 }
  const days = smartDays[tf] || 90
  setDatePreset({ id: '__smart', label: '', days })
}

onMounted(() => {
  if (!startDate.value || !endDate.value) applySmartDefault()
})

// 切换 timeframe 时, 同步重置到合理默认 (避免分钟级 1d 跨 1 年 -> 50万行)
// 标记 autoRangeDisabled, 用户后续手动选过的就不再被覆盖
const autoRangeDisabled = ref(false)
watch(timeframe, () => applySmartDefault())
</script>

<template>
  <div class="kline-binance" :class="{ fullscreen }">
    <!-- 顶部: 交易对 + 价格信息 (Binance 风格) -->
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
        <div class="header-stats">
          <div class="stat-block">
            <div class="stat-lbl">{{ symbol }} 价格</div>
            <div class="stat-val price" :class="priceChange >= 0 ? 'pos' : 'neg'">
              {{ lastPrice != null ? lastPrice.toFixed(lastPrice < 1 ? 4 : 2) : '-' }}
            </div>
          </div>
          <div class="stat-block">
            <div class="stat-lbl">涨跌</div>
            <div class="stat-val" :class="priceChange >= 0 ? 'pos' : 'neg'">
              <span v-if="priceChange != null">{{ priceChange >= 0 ? '+' : '' }}{{ priceChange.toFixed(2) }}</span>
              <span v-if="priceChangePct != null" class="pct">
                ({{ priceChangePct >= 0 ? '+' : '' }}{{ (priceChangePct * 100).toFixed(2) }}%)
              </span>
            </div>
          </div>
          <div class="stat-block">
            <div class="stat-lbl">区间最高</div>
            <div class="stat-val pos">{{ high24 != null ? high24.toFixed(2) : '-' }}</div>
          </div>
          <div class="stat-block">
            <div class="stat-lbl">区间最低</div>
            <div class="stat-val neg">{{ low24 != null ? low24.toFixed(2) : '-' }}</div>
          </div>
          <div class="stat-block">
            <div class="stat-lbl">区间成交量</div>
            <div class="stat-val">{{ fmtBig(vol24) }}</div>
          </div>
          <div class="stat-block">
            <div class="stat-lbl">K线数</div>
            <div class="stat-val">{{ stats.rows || 0 }}</div>
          </div>
        </div>
      </div>
      <div class="header-actions">
        <button class="icon-btn" :class="{ active: fullscreen }" @click="toggleFullscreen" :title="fullscreen ? '退出全屏' : '全屏'">
          {{ fullscreen ? '⛶' : '⛶' }}
        </button>
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
        <span class="date-range-label">
          {{ startDate || '?' }} → {{ endDate || '?' }}
        </span>
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
        <button :class="{ active: tableView === 'chart' }" @click="tableView = 'chart'">📈 图表</button>
        <button :class="{ active: tableView === 'table' }" @click="tableView = 'table'">📋 数据</button>
      </div>
    </div>

    <!-- 主图区 -->
    <div v-if="tableView === 'chart'" class="chart-area">
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

/* 顶部报价区 (Binance 风) */
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
.symbol-list {
  max-height: 360px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
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
.sym-cat {
  font-size: 9px;
  background: var(--bg-elevated);
  color: var(--text-muted);
  padding: 1px 6px;
  border-radius: 8px;
}
.empty { padding: 30px; text-align: center; color: var(--text-muted); font-size: 12px; }

.header-stats { display: flex; gap: 20px; flex-wrap: wrap; }
.stat-block { display: flex; flex-direction: column; gap: 2px; }
.stat-lbl { font-size: 10px; color: var(--text-muted); }
.stat-val { font-size: 16px; font-weight: 600; font-family: 'Consolas', monospace; }
.stat-val.price { font-size: 20px; }
.stat-val.pos { color: var(--green); }
.stat-val.neg { color: var(--red); }
.pct { font-size: 12px; margin-left: 4px; }

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
.tf-tabs button.active {
  background: var(--yellow);
  color: #000;
}
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
.date-range-label {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  font-family: 'Consolas', monospace;
}

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
  display: inline-flex;
  align-items: center;
  gap: 4px;
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
.indicator-bar button.active {
  background: rgba(240,185,11,0.15);
  border-color: var(--yellow);
  color: var(--yellow);
}

/* 主图区 */
.chart-area {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  min-height: 500px;
}
.chart { height: 600px; }
.fullscreen .chart-area { height: calc(100vh - 240px); display: flex; flex-direction: column; }
.fullscreen .chart { flex: 1; min-height: 400px; }
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

.dropdown-enter-active, .dropdown-leave-active { transition: opacity 0.15s, transform 0.15s; }
.dropdown-enter-from, .dropdown-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
