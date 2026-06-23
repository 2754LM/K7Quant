<script setup>
import { ref, computed, watch, nextTick, inject, onUnmounted, onMounted } from 'vue'
import { getKline } from '../api'
import * as echarts from 'echarts'
import { subscribeKline, closeAllStreams } from '../utils/binance-ws'
import { tfLabel } from '../utils/timeframe'
import { useTimeframes } from '../composables/useTimeframes'

const cfg = inject('cfg')

// ============ 全局状态 ============
const symbolInfo = computed(() => {
  const m = {}
  for (const s of cfg.value?.symbols || []) m[s.symbol] = s
  return m
})
const allSymbols = computed(() => (cfg.value?.symbols || []).map(s => s.symbol))
const { list: timeframes } = useTimeframes()  // 从后端拉 Binance 白名单
const MA_COLORS = ['#9b59b6', '#3498db', '#e67e22', '#f1c40f', '#f0b90b', '#e74c3c', '#1abc9c', '#16a085']

// ============ 面板系统 ============
// 每个 panel: { id, symbol, timeframe, startDate, endDate, indicators, data, loading, error, live, unsub, chart }
// indicators: { ma:{enabled,periods}, ema:{...}, boll:{...}, macd:{...}, rsi:{...}, kdj:{...}, volume:bool }

const panels = ref([])      // 数组, 每个 panel 独立, 自由拖动排序

function makePanel(idx, template = null) {
  const t = template || {}
  return {
    id: `panel-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 6)}`,
    symbol: t.symbol || 'BTCUSDT',
    timeframe: t.timeframe || '4h',
    startDate: '',
    endDate: '',
    indicators: t.indicators ? JSON.parse(JSON.stringify(t.indicators)) : {
      ma:   { enabled: true,  periods: [5, 10, 20, 30, 60] },
      ema:  { enabled: false, periods: [12, 26] },
      boll: { enabled: false, period: 20, std: 2 },
      macd: { enabled: false, fast: 12, slow: 26, signal: 9 },
      rsi:  { enabled: false, period: 14 },
      kdj:  { enabled: false, n: 9, m1: 3, m2: 3 },
      volume: true,
    },
    data: null,
    loading: false,
    error: '',
    live: false,
    wsUnsub: null,
    lastTick: null,
    chart: null,
  }
}

// 初始化
panels.value = [makePanel(0)]
nextTick(() => {
  applySmartDefault(panels.value[0])
  loadPanel(panels.value[0])
})

// 添加新面板: 复制最后一个的设置
function addPanel() {
  const last = panels.value[panels.value.length - 1]
  const np = makePanel(panels.value.length, {
    symbol: last?.symbol,
    timeframe: last?.timeframe,
    indicators: last?.indicators,
  })
  panels.value.push(np)
  registerPanelWatchers(np)
  nextTick(() => {
    applySmartDefault(np)
    loadPanel(np)
  })
}

// 单 panel 模式: 通过顶部 "添加面板" 按钮新增 (复制最后一个设置)
// 没有拖动排序/复制/关闭, 避免和 ECharts dataZoom 冲突

// ============ 智能默认日期 ============
function applySmartDefault(p) {
  const tf = p.timeframe
  const smartDays = { '1m': 7, '5m': 14, '15m': 30, '30m': 60, '1h': 90, '4h': 180, '1d': 365, '1w': 730 }
  const days = smartDays[tf] || 90
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - days)
  p.startDate = start.toISOString().slice(0, 10).replace(/-/g, '')
  p.endDate = end.toISOString().slice(0, 10).replace(/-/g, '')
}
function applySmartDefaultAll() {
  for (const p of panels.value) {
    applySmartDefault(p)
    loadPanel(p)
  }
}

// 点 tf 按钮: 如果换周期, 自动调日期范围并重载
function onTimeframeClick(p, tf) {
  if (p.timeframe === tf) return
  p.timeframe = tf
  applySmartDefault(p)
  loadPanel(p)
}

// ============ 加载 K 线 ============
async function loadPanel(p) {
  if (!p.startDate || !p.endDate) return
  p.loading = true
  p.error = ''
  p.clamped = false
  p.clampMsg = ''
  try {
    const res = await getKline(p.symbol, p.timeframe, p.startDate, p.endDate)
    if (res.data.error) {
      p.error = res.data.error
      p.data = null
    } else {
      p.data = res.data
      if (res.data.clamped) {
        p.clamped = true
        p.clampMsg = res.data.clamp_msg || ''
      }
      await nextTick()
      drawPanel(p)
    }
  } catch (e) {
    p.error = e.message
  } finally {
    p.loading = false
  }
}

// 数据 / 指标变化时重绘 (注册到每个 panel)
function registerPanelWatchers(p) {
  watch(() => [p.symbol, p.startDate, p.endDate], () => loadPanel(p))
  watch(() => p.indicators, () => drawPanel(p), { deep: true })
}
for (const p of panels.value) registerPanelWatchers(p)

// ============ 实时模式 ============
function toggleLive(p) {
  if (p.live) {
    // 关
    p.live = false
    if (p.wsUnsub) { p.wsUnsub(); p.wsUnsub = null }
  } else {
    // 开
    p.live = true
    if (!p.data?.kline?.length) {
      loadPanel(p).then(() => startWs(p))
    } else {
      startWs(p)
    }
  }
}

function startWs(p) {
  if (p.wsUnsub) p.wsUnsub()
  p.wsUnsub = subscribeKline(p.symbol, p.timeframe, (bar) => {
    if (!p.data?.kline?.length) return
    const klines = p.data.kline
    const lastDateMs = new Date(klines[klines.length - 1].date).getTime()
    if (bar.time >= lastDateMs) {
      // 同根或新根
      if (bar.time === lastDateMs) {
        // 替换最后一根
        klines[klines.length - 1] = {
          date: new Date(bar.time).toISOString().slice(0, 10),
          open: bar.open, high: bar.high, low: bar.low, close: bar.close,
          volume: bar.volume,
        }
      } else {
        // 新增一根 (WS 推送的根比历史数据新, 说明是新生成的一根)
        klines.push({
          date: new Date(bar.time).toISOString().slice(0, 10),
          open: bar.open, high: bar.high, low: bar.low, close: bar.close,
          volume: bar.volume,
        })
        // 移除第一根避免无限增长
        if (klines.length > 2000) klines.shift()
      }
      p.lastTick = Date.now()
      drawPanel(p)
    }
  })
}

// ============ 指标计算 ============
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

// ============ 绘图 (单 panel) ============
function drawPanel(p) {
  if (!p.data?.kline?.length) return
  const elId = `chart-${p.id}`
  const el = document.getElementById(elId)
  if (!el) return
  if (!p.chart || p.chart.getDom() !== el) {
    if (p.chart) { try { p.chart.dispose() } catch {} }
    p.chart = echarts.init(el, null, { renderer: 'canvas' })
  }
  const c = p.chart
  const kline = p.data.kline
  const dates = kline.map(k => k.date)
  const closes = kline.map(k => k.close)
  const highs = kline.map(k => k.high)
  const lows = kline.map(k => k.low)
  const kValues = kline.map(k => [k.open, k.close, k.low, k.high])

  const ind = p.indicators
  const subCount = [ind.volume, ind.macd.enabled, ind.rsi.enabled, ind.kdj.enabled].filter(Boolean).length
  const MAIN_H = 70
  const SUB_H = subCount > 0 ? Math.min(15, 24 / Math.max(1, subCount)) : 0
  const GAP = 3

  const grids = []
  const xAxes = []
  const yAxes = []
  const series = []

  grids.push({ left: 50, right: 70, top: 18, height: `${MAIN_H}%` })
  xAxes.push({ type: 'category', data: dates, gridIndex: 0, axisLine: { lineStyle: { color: '#2b3139' } }, axisLabel: { show: false } })
  yAxes.push({ scale: true, gridIndex: 0, position: 'right', splitLine: { lineStyle: { color: '#2b3139', type: 'dashed' } }, axisLabel: { color: '#b7bdc6', fontSize: 10 } })

  series.push({
    name: 'K线', type: 'candlestick', data: kValues,
    xAxisIndex: 0, yAxisIndex: 0,
    itemStyle: { color: '#02c076', color0: '#f6465d', borderColor: '#02c076', borderColor0: '#f6465d' },
  })

  if (ind.ma.enabled) {
    ind.ma.periods.forEach((n, i) => {
      const ma = computeMA(closes, n)
      series.push({
        name: `MA${n}`, type: 'line', data: ma, smooth: true, showSymbol: false,
        xAxisIndex: 0, yAxisIndex: 0,
        lineStyle: { width: 1.2, color: MA_COLORS[i % MA_COLORS.length] },
      })
    })
  }
  if (ind.ema.enabled) {
    ind.ema.periods.forEach((n, i) => {
      const ema = computeEMA(closes, n)
      series.push({
        name: `EMA${n}`, type: 'line', data: ema, smooth: true, showSymbol: false,
        xAxisIndex: 0, yAxisIndex: 0,
        lineStyle: { width: 1.2, color: MA_COLORS[(i + 4) % MA_COLORS.length], type: 'dashed' },
      })
    })
  }
  if (ind.boll.enabled) {
    const b = computeBOLL(closes, ind.boll.period, ind.boll.std)
    series.push({ name: 'BOLL上', type: 'line', data: b.upper, smooth: true, showSymbol: false, xAxisIndex: 0, yAxisIndex: 0, lineStyle: { width: 0.8, color: '#8e44ad', opacity: 0.5 } })
    series.push({ name: 'BOLL中', type: 'line', data: b.mid, smooth: true, showSymbol: false, xAxisIndex: 0, yAxisIndex: 0, lineStyle: { width: 0.8, color: '#8e44ad', opacity: 0.7 } })
    series.push({ name: 'BOLL下', type: 'line', data: b.lower, smooth: true, showSymbol: false, xAxisIndex: 0, yAxisIndex: 0, lineStyle: { width: 0.8, color: '#8e44ad', opacity: 0.5 } })
  }

  let subIdx = 1
  let topPos = MAIN_H + GAP
  const subConfigs = []
  if (ind.volume) subConfigs.push('volume')
  if (ind.macd.enabled) subConfigs.push('macd')
  if (ind.rsi.enabled) subConfigs.push('rsi')
  if (ind.kdj.enabled) subConfigs.push('kdj')

  for (const sub of subConfigs) {
    grids.push({ left: 50, right: 70, top: `${topPos}%`, height: `${SUB_H}%` })
    xAxes.push({ type: 'category', data: dates, gridIndex: subIdx, axisLine: { lineStyle: { color: '#2b3139' } }, axisLabel: subIdx === subConfigs.length ? { color: '#b7bdc6', fontSize: 10 } : { show: false } })
    yAxes.push({ gridIndex: subIdx, position: 'right', splitLine: { show: false }, axisLabel: { color: '#b7bdc6', fontSize: 10 } })

    if (sub === 'volume') {
      series.push({
        name: '成交量', type: 'bar', xAxisIndex: subIdx, yAxisIndex: subIdx,
        data: kline.map(k => ({
          value: k.volume || 0,
          itemStyle: { color: k.close >= k.open ? 'rgba(2,192,118,0.6)' : 'rgba(246,70,93,0.6)' },
        })),
      })
    } else if (sub === 'macd') {
      const m = computeMACD(closes, ind.macd.fast, ind.macd.slow, ind.macd.signal)
      series.push({ name: 'DIF', type: 'line', data: m.dif, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx, lineStyle: { width: 1, color: '#f0b90b' } })
      series.push({ name: 'DEA', type: 'line', data: m.dea, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx, lineStyle: { width: 1, color: '#3498db' } })
      series.push({ name: 'MACD', type: 'bar', xAxisIndex: subIdx, yAxisIndex: subIdx,
        data: m.hist.map(v => ({ value: v == null ? 0 : v, itemStyle: { color: v == null ? 'transparent' : (v >= 0 ? 'rgba(2,192,118,0.7)' : 'rgba(246,70,93,0.7)') } })),
      })
    } else if (sub === 'rsi') {
      const rsi = computeRSI(closes, ind.rsi.period)
      series.push({ name: `RSI${ind.rsi.period}`, type: 'line', data: rsi, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx,
        lineStyle: { width: 1.2, color: '#f0b90b' },
        markLine: { silent: true, symbol: 'none', data: [
          { yAxis: 20, lineStyle: { color: '#f6465d', type: 'dashed' } },
          { yAxis: 80, lineStyle: { color: '#02c076', type: 'dashed' } },
        ] },
      })
    } else if (sub === 'kdj') {
      const kdj = computeKDJ(closes, highs, lows, ind.kdj.n, ind.kdj.m1, ind.kdj.m2)
      series.push({ name: 'K', type: 'line', data: kdj.k, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx, lineStyle: { width: 1, color: '#f0b90b' } })
      series.push({ name: 'D', type: 'line', data: kdj.d, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx, lineStyle: { width: 1, color: '#3498db' } })
      series.push({ name: 'J', type: 'line', data: kdj.j, showSymbol: false, xAxisIndex: subIdx, yAxisIndex: subIdx, lineStyle: { width: 1, color: '#9b59b6' } })
    }
    subIdx++
    topPos += SUB_H + GAP
  }

  const dataZoom = [
    { type: 'inside', xAxisIndex: grids.map((_, i) => i) },
    { type: 'slider', xAxisIndex: grids.map((_, i) => i), height: 16, bottom: 4, backgroundColor: '#181a20' },
  ]

  const lastPrice = kline[kline.length - 1].close
  const markLine = {
    silent: true, symbol: 'none',
    data: [{ yAxis: lastPrice, lineStyle: { color: '#f0b90b', type: 'dashed', width: 0.8 }, label: { show: false } }],
  }

  const option = {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }] },
      backgroundColor: 'rgba(24,26,32,0.95)', borderColor: '#474d57',
      textStyle: { color: '#eaecef', fontSize: 11 },
      formatter: (params) => {
        if (!params || !params.length) return ''
        const candle = params.find(p => p.seriesType === 'candlestick')
        if (!candle) return params.map(pp => `${pp.marker} ${pp.seriesName}: <b>${pp.value}</b>`).join('<br/>') + `<br/><span style="color:#888">${params[0].axisValueLabel}</span>`
        const d = candle.data || []
        const o = d[0], c = d[1], l = d[2], h = d[3]
        if (o == null || c == null) return ''
        const chg = c - o
        const chgPct = o ? (chg / o * 100).toFixed(2) : '0.00'
        const color = chg >= 0 ? '#02c076' : '#f6465d'
        let html = `<div style="font-weight:600;margin-bottom:4px">${candle.axisValueLabel}</div>`
        html += `<table style="font-family:Consolas,monospace;font-size:11px">`
        html += `<tr><td>开</td><td style="text-align:right"><b>${(+o).toFixed(2)}</b></td></tr>`
        html += `<tr><td>收</td><td style="text-align:right;color:${color}"><b>${(+c).toFixed(2)} (${chg >= 0 ? '+' : ''}${chgPct}%)</b></td></tr>`
        html += `<tr><td>高</td><td style="text-align:right;color:#02c076">${(+h).toFixed(2)}</td></tr>`
        html += `<tr><td>低</td><td style="text-align:right;color:#f6465d">${(+l).toFixed(2)}</td></tr>`
        for (const pp of params) {
          if (pp.seriesType === 'candlestick') continue
          if (pp.value == null || pp.value === '') continue
          let v = pp.value
          if (typeof v === 'number') v = Math.abs(v) < 1 ? v.toFixed(4) : v.toFixed(2)
          html += `<tr><td>${pp.marker} ${pp.seriesName}</td><td style="text-align:right">${v}</td></tr>`
        }
        html += `</table>`
        return html
      },
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    xAxis: xAxes, yAxis: yAxes, grid: grids, series, dataZoom,
    legend: { show: true, top: 2, textStyle: { color: '#b7bdc6', fontSize: 10 }, itemWidth: 14, itemHeight: 8 },
  }
  try {
    c.setOption(option, { notMerge: true })
  } catch (e) {
    console.warn('[KLine] drawPanel fail:', e)
  }
}

// 全局监听窗口尺寸
let resizeHandler = null
onMounted(() => {
  resizeHandler = () => {
    for (const p of panels.value) {
      if (p.chart) p.chart.resize()
    }
  }
  window.addEventListener('resize', resizeHandler)
})
onUnmounted(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  for (const p of panels.value) {
    if (p.wsUnsub) p.wsUnsub()
    if (p.chart) { try { p.chart.dispose() } catch {} }
  }
  closeAllStreams()
})

// 工具
function fmtPrice(v, last) {
  if (v == null) return '—'
  const decimals = last != null && last < 1 ? 4 : last != null && last < 100 ? 3 : 2
  return v.toFixed(decimals)
}
function fmtBig(v) {
  if (v == null) return '—'
  if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(2) + 'K'
  return v.toFixed(2)
}
function fmtTime(s) {
  if (!s) return ''
  if (s.length === 10 && s.includes('-')) return s.slice(5)
  if (s.length === 8) return `${s.slice(4, 6)}-${s.slice(6, 8)}`
  return s
}

// 指标编辑
function addPeriod(p, key, defaultVal) {
  p.indicators[key].periods.push(defaultVal)
}
function removePeriod(p, key, i) {
  p.indicators[key].periods.splice(i, 1)
}
function editPeriod(p, key, i, v) {
  const n = parseInt(v, 10)
  if (!isNaN(n) && n > 0) p.indicators[key].periods[i] = n
}

// 副 panel 缩略计算: 最后一根 K 线
function lastBar(p) {
  if (!p.data?.kline?.length) return null
  return p.data.kline[p.data.kline.length - 1]
}
function prevClose(p) {
  const k = p.data?.kline
  if (!k || k.length < 2) return null
  return k[k.length - 2].close
}
function priceChange(p) {
  const lb = lastBar(p), pc = prevClose(p)
  if (!lb || pc == null) return null
  return lb.close - pc
}
function priceChangePct(p) {
  const lb = lastBar(p), pc = prevClose(p)
  if (!lb || pc == null || !pc) return null
  return (lb.close - pc) / pc
}

// 日期预设 (per panel)
const datePresets = [
  { id: '1w', label: '1周', days: 7 },
  { id: '1m', label: '1月', days: 30 },
  { id: '3m', label: '3月', days: 90 },
  { id: '6m', label: '6月', days: 180 },
  { id: '1y', label: '1年', days: 365 },
  { id: '2y', label: '2年', days: 730 },
]
function setDatePreset(p, preset) {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - preset.days)
  p.startDate = start.toISOString().slice(0, 10).replace(/-/g, '')
  p.endDate = end.toISOString().slice(0, 10).replace(/-/g, '')
  loadPanel(p)
}
</script>

<template>
  <div class="kline-multipanel">
    <!-- 顶部: 添加面板 + 总览 -->
    <div class="topbar">
      <div class="topbar-right">
        <button class="add-panel-btn" @click="addPanel" title="新增一个面板 (复制最后一个的设置)">
          ➕ 添加面板
        </button>
      </div>
    </div>

    <!-- 自由堆叠的卡片列表 -->
    <div class="panels-stack">
      <div v-for="(p, idx) in panels" :key="p.id" class="panel-card"
        :class="{ single: panels.length === 1 }">
        <!-- Panel 工具栏 (无拖动/复制/关闭按钮, 用顶部"添加面板"新增) -->
        <div class="panel-toolbar">
          <div class="pt-row1">
            <select v-model="p.symbol" class="symbol-sel" @change="loadPanel(p)">
              <option v-for="s in allSymbols" :key="s" :value="s">{{ symbolInfo[s]?.name_zh || s }} ({{ s }})</option>
            </select>
            <div class="tf-mini">
              <button v-for="tf in timeframes" :key="tf"
                :class="{ active: tf === p.timeframe }"
                @click="onTimeframeClick(p, tf)">{{ tf }}</button>
            </div>
            <button class="live-btn" :class="{ on: p.live }" @click="toggleLive(p)" :title="p.live ? '关闭实时 (WebSocket)' : '开启实时 (WebSocket 订阅 Binance)'">
              <span class="dot" :class="{ pulse: p.live }"></span>
              {{ p.live ? 'LIVE' : '实时' }}
            </button>
          </div>
          <div class="pt-row2">
            <span class="date-presets">
              <button v-for="dp in datePresets" :key="dp.id"
                @click="setDatePreset(p, dp)">{{ dp.label }}</button>
            </span>
            <span class="date-range">{{ fmtTime(p.startDate) }} → {{ fmtTime(p.endDate) }}</span>
          </div>
        </div>

        <!-- 报价区 (Binance 风格) -->
        <div class="quote-bar" v-if="lastBar(p)">
          <div class="price-main" :class="priceChange(p) >= 0 ? 'pos' : 'neg'">
            {{ fmtPrice(lastBar(p).close, lastBar(p).close) }}
          </div>
          <div class="quote-meta">
            <span class="chg" :class="priceChange(p) >= 0 ? 'pos' : 'neg'">
              {{ priceChange(p) != null ? (priceChange(p) >= 0 ? '+' : '') + priceChange(p).toFixed(2) : '—' }}
              ({{ priceChangePct(p) != null ? (priceChangePct(p) >= 0 ? '+' : '') + (priceChangePct(p) * 100).toFixed(2) + '%' : '—' }})
            </span>
            <span class="sep">·</span>
            <span class="oh"><span class="oh-lbl">开</span>{{ fmtPrice(lastBar(p).open, lastBar(p).close) }}</span>
            <span class="oh"><span class="oh-lbl">高</span><span class="pos">{{ fmtPrice(lastBar(p).high, lastBar(p).close) }}</span></span>
            <span class="oh"><span class="oh-lbl">低</span><span class="neg">{{ fmtPrice(lastBar(p).low, lastBar(p).close) }}</span></span>
            <span class="oh"><span class="oh-lbl">量</span>{{ fmtBig(lastBar(p).volume) }}</span>
          </div>
        </div>

        <!-- 指标配置 (折叠面板, 默认展开) -->
        <details class="indicator-config" open>
          <summary>⚙ 指标</summary>
          <div class="ind-grid">
            <!-- MA -->
            <div class="ind-block">
              <label class="ind-toggle">
                <input type="checkbox" v-model="p.indicators.ma.enabled" />
                <span>MA</span>
              </label>
              <div v-if="p.indicators.ma.enabled" class="ind-params">
                <div v-for="(n, i) in p.indicators.ma.periods" :key="i" class="period-tag">
                  <input type="number" :value="n" @change="editPeriod(p, 'ma', i, $event.target.value)" min="1" max="500" />
                  <button @click="removePeriod(p, 'ma', i)">×</button>
                </div>
                <button class="add-btn" @click="addPeriod(p, 'ma', 20)">+ 周期</button>
              </div>
            </div>
            <!-- EMA -->
            <div class="ind-block">
              <label class="ind-toggle">
                <input type="checkbox" v-model="p.indicators.ema.enabled" />
                <span>EMA</span>
              </label>
              <div v-if="p.indicators.ema.enabled" class="ind-params">
                <div v-for="(n, i) in p.indicators.ema.periods" :key="i" class="period-tag">
                  <input type="number" :value="n" @change="editPeriod(p, 'ema', i, $event.target.value)" min="1" max="500" />
                  <button @click="removePeriod(p, 'ema', i)">×</button>
                </div>
                <button class="add-btn" @click="addPeriod(p, 'ema', 26)">+ 周期</button>
              </div>
            </div>
            <!-- BOLL -->
            <div class="ind-block">
              <label class="ind-toggle">
                <input type="checkbox" v-model="p.indicators.boll.enabled" />
                <span>BOLL</span>
              </label>
              <div v-if="p.indicators.boll.enabled" class="ind-params">
                <label>周期 <input type="number" v-model.number="p.indicators.boll.period" min="2" max="200" /></label>
                <label>σ倍数 <input type="number" step="0.1" v-model.number="p.indicators.boll.std" min="0.5" max="5" /></label>
              </div>
            </div>
            <!-- 副图 -->
            <div class="ind-block">
              <span class="ib-lbl">副图</span>
              <div class="sub-checks">
                <label><input type="checkbox" v-model="p.indicators.volume" /> 成交量</label>
                <label><input type="checkbox" v-model="p.indicators.macd.enabled" /> MACD</label>
                <label><input type="checkbox" v-model="p.indicators.rsi.enabled" /> RSI</label>
                <label><input type="checkbox" v-model="p.indicators.kdj.enabled" /> KDJ</label>
              </div>
            </div>
            <!-- 副图参数 -->
            <div v-if="p.indicators.macd.enabled" class="ind-block">
              <span class="ib-lbl">MACD 参数</span>
              <div class="ind-params">
                <label>快 <input type="number" v-model.number="p.indicators.macd.fast" min="2" max="60" /></label>
                <label>慢 <input type="number" v-model.number="p.indicators.macd.slow" min="5" max="120" /></label>
                <label>信号 <input type="number" v-model.number="p.indicators.macd.signal" min="2" max="50" /></label>
              </div>
            </div>
            <div v-if="p.indicators.rsi.enabled" class="ind-block">
              <span class="ib-lbl">RSI 参数</span>
              <div class="ind-params">
                <label>周期 <input type="number" v-model.number="p.indicators.rsi.period" min="2" max="50" /></label>
              </div>
            </div>
            <div v-if="p.indicators.kdj.enabled" class="ind-block">
              <span class="ib-lbl">KDJ 参数</span>
              <div class="ind-params">
                <label>N <input type="number" v-model.number="p.indicators.kdj.n" min="3" max="50" /></label>
                <label>M1 <input type="number" v-model.number="p.indicators.kdj.m1" min="1" max="10" /></label>
                <label>M2 <input type="number" v-model.number="p.indicators.kdj.m2" min="1" max="10" /></label>
              </div>
            </div>
          </div>
        </details>

        <!-- 图表区 -->
        <div class="panel-chart-wrap">
          <div v-if="p.loading && !p.data" class="loading-state">
            <div class="spinner"></div>
            <span>加载 {{ p.symbol }} {{ p.timeframe }}...</span>
          </div>
          <div v-else-if="p.error" class="error-state">⚠ {{ p.error }}</div>
          <div v-show="p.data?.kline?.length" :id="`chart-${p.id}`" class="chart"></div>
        </div>
        <!-- clamp 提示 -->
        <div v-if="p.clamped" class="clamp-banner" :title="p.clampMsg">
          ⚠ {{ p.clampMsg || '已截取到缓存实际范围' }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kline-multipanel { display: flex; flex-direction: column; gap: 12px; height: 100%; }

/* 顶部 */
.topbar {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 14px;
}
.topbar-left .hint { font-size: 11px; color: var(--text-muted); }
.add-panel-btn {
  background: var(--bg); border: 1px solid var(--yellow); color: var(--yellow);
  padding: 6px 14px; border-radius: 6px; font-size: 12px;
  cursor: pointer; font-weight: 600;
}
.add-panel-btn:hover { background: var(--yellow); color: #000; }

/* 自由堆叠的卡片 */
.panels-stack { display: flex; flex-direction: column; gap: 12px; flex: 1; min-height: 0; overflow-y: auto; padding: 2px; }

/* Panel */
.panel-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; padding: 10px;
  display: flex; flex-direction: column; gap: 6px; min-height: 0;
  min-width: 0; position: relative;
  transition: border-color 0.15s, transform 0.15s;
}
.panel-card:hover { border-color: rgba(240,185,11,0.3); }
.panel-card.single { min-height: 500px; }

/* clamp 提示 */
.clamp-banner {
  background: rgba(240,185,11,0.08);
  border: 1px solid rgba(240,185,11,0.3);
  border-radius: 4px; padding: 6px 10px;
  font-size: 11px; color: var(--yellow);
}

/* 工具栏 */
.panel-toolbar { display: flex; flex-direction: column; gap: 4px; }
.pt-row1 { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.pt-row2 { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }

.symbol-sel {
  background: var(--bg); border: 1px solid var(--border); color: var(--text);
  padding: 4px 8px; border-radius: 4px; font-size: 12px;
  max-width: 180px; cursor: pointer;
}
.symbol-sel:focus { outline: none; border-color: var(--yellow); }

.tf-mini { display: flex; gap: 1px; }
.tf-mini button {
  background: var(--bg); border: 1px solid var(--border); color: var(--text-secondary);
  padding: 3px 8px; font-size: 10px; cursor: pointer;
}
.tf-mini button:first-child { border-radius: 4px 0 0 4px; }
.tf-mini button:last-child { border-radius: 0 4px 4px 0; }
.tf-mini button.active { background: var(--yellow); color: #000; font-weight: 600; border-color: var(--yellow); }
.tf-mini button:hover:not(.active) { color: var(--yellow); }

.live-btn {
  background: var(--bg); border: 1px solid var(--border); color: var(--text-secondary);
  padding: 3px 10px; border-radius: 4px; font-size: 11px;
  display: flex; align-items: center; gap: 6px; cursor: pointer;
  margin-left: auto;
}
.live-btn:hover { border-color: var(--red); }
.live-btn.on { background: rgba(246,70,93,0.15); border-color: var(--red); color: var(--red); font-weight: 600; }
.live-btn .dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted);
}
.live-btn.on .dot { background: var(--red); }
.live-btn.on .dot.pulse { animation: live-pulse 1.5s ease-in-out infinite; }
@keyframes live-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.4); }
}

.close-btn {
  background: transparent; border: 1px solid var(--border); color: var(--text-muted);
  width: 22px; height: 22px; border-radius: 4px; font-size: 14px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.close-btn:hover { border-color: var(--red); color: var(--red); }

.date-presets { display: flex; gap: 2px; }
.date-presets button {
  background: var(--bg); border: 1px solid var(--border); color: var(--text-secondary);
  padding: 2px 8px; font-size: 10px; border-radius: 3px; cursor: pointer;
}
.date-presets button:hover { color: var(--yellow); border-color: var(--yellow); }

.date-range {
  font-size: 10px; color: var(--text-muted);
  font-family: 'Consolas', monospace;
  margin-left: auto;
}

/* 报价区 */
.quote-bar {
  display: flex; align-items: center; gap: 14px;
  padding: 4px 6px;
  background: var(--bg);
  border-radius: 4px;
}
.price-main {
  font-size: 22px; font-weight: 700;
  font-family: 'Consolas', monospace;
  letter-spacing: -0.5px;
}
.price-main.pos { color: var(--green, #02c076); }
.price-main.neg { color: var(--red, #f6465d); }
.quote-meta { display: flex; gap: 10px; align-items: center; font-size: 11px; flex-wrap: wrap; }
.chg { font-family: 'Consolas', monospace; font-weight: 600; }
.chg.pos { color: var(--green); }
.chg.neg { color: var(--red); }
.sep { color: var(--text-muted); }
.oh { display: inline-flex; gap: 4px; align-items: center; font-family: 'Consolas', monospace; }
.oh-lbl { color: var(--text-muted); font-size: 10px; }
.oh .pos { color: var(--green); }
.oh .neg { color: var(--red); }

/* 指标配置 */
.indicator-config {
  background: var(--bg); border-radius: 4px;
  border: 1px solid var(--border);
  font-size: 11px;
}
.indicator-config > summary {
  padding: 4px 8px; cursor: pointer; color: var(--text-secondary);
  user-select: none;
}
.indicator-config > summary:hover { color: var(--yellow); }
.ind-grid {
  display: flex; flex-wrap: wrap; gap: 8px;
  padding: 6px 8px;
  border-top: 1px solid var(--border);
}
.ind-block {
  display: flex; flex-direction: column; gap: 4px;
  background: var(--bg-card);
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--border);
  min-width: 100px;
}
.ind-toggle {
  display: flex; align-items: center; gap: 4px; font-size: 11px;
  font-weight: 600;
}
.ind-toggle input { accent-color: var(--yellow); }
.ind-params { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.ind-params label { display: flex; gap: 3px; align-items: center; font-size: 10px; color: var(--text-muted); }
.ind-params input[type="number"] {
  width: 50px; padding: 2px 4px;
  background: var(--bg); border: 1px solid var(--border);
  color: var(--text); border-radius: 3px; font-size: 11px;
  font-family: 'Consolas', monospace;
}
.ind-params input[type="number"]:focus { outline: none; border-color: var(--yellow); }

.period-tag {
  display: flex; align-items: center; gap: 2px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 4px;
}
.period-tag input {
  width: 36px; border: none; background: transparent;
  color: var(--text); font-size: 11px;
  font-family: 'Consolas', monospace; text-align: center;
}
.period-tag input:focus { outline: none; }
.period-tag button {
  background: transparent; border: none; color: var(--text-muted);
  font-size: 12px; padding: 0 2px; cursor: pointer;
}
.period-tag button:hover { color: var(--red); }
.add-btn {
  background: transparent; border: 1px dashed var(--border); color: var(--text-muted);
  padding: 1px 6px; border-radius: 3px; font-size: 10px; cursor: pointer;
}
.add-btn:hover { color: var(--yellow); border-color: var(--yellow); }

.ib-lbl { font-size: 10px; color: var(--text-muted); margin-bottom: 2px; }
.sub-checks { display: flex; flex-wrap: wrap; gap: 6px; }
.sub-checks label {
  display: flex; align-items: center; gap: 3px;
  font-size: 10px; color: var(--text-secondary);
}
.sub-checks input { accent-color: var(--yellow); }

/* 图表区 */
.panel-chart-wrap { flex: 1; position: relative; min-height: 0; min-width: 0; }
.chart { width: 100%; height: 100%; min-height: 320px; }
.loading-state, .error-state {
  position: absolute; inset: 0; display: flex;
  align-items: center; justify-content: center; flex-direction: column;
  gap: 8px; color: var(--text-muted); font-size: 13px;
}
.error-state { color: var(--red); }
.spinner {
  width: 24px; height: 24px;
  border: 2px solid var(--border);
  border-top-color: var(--yellow);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>