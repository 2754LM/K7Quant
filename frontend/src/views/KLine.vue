<script setup>
import { ref, computed, watch, nextTick, inject, onUnmounted } from 'vue'
import { getKline } from '../api'
import * as echarts from 'echarts'

import TimeframePicker from '../components/TimeframePicker.vue'
import DateRangePicker from '../components/DateRangePicker.vue'
import StateView from '../components/StateView.vue'
import HelpTip from '../components/HelpTip.vue'

const cfg = inject('cfg')

const symbol = ref('BTCUSDT')
const timeframe = ref('4h')
const startDate = ref('20240101')
const endDate = ref('20250601')
const data = ref(null)
const loading = ref(false)
const error = ref('')
const tableView = ref('chart')
const visibleIndicators = ref({
  ma7: true, ma25: true, ma99: false,
  ma5: false, ma10: false, ma20: false, ma60: false,
  boll: false, ema: false,
  volume: true,
})
let chart = null

const symbolInfo = computed(() => {
  const m = {}
  for (const s of cfg.value?.symbols || []) m[s.symbol] = s
  return m
})
const timeframes = computed(() => cfg.value?.timeframes || ['1d'])
const allSymbols = computed(() => (cfg.value?.symbols || []).map(s => s.symbol))

const curInfo = computed(() => symbolInfo.value[symbol.value] || {})
const stats = computed(() => data.value?.stats || {})
const tableRows = computed(() => {
  if (!data.value?.kline) return []
  return data.value.kline.slice(-200).reverse()
})

watch([symbol, timeframe], () => load(), { immediate: true })
watch(visibleIndicators, () => drawChart(), { deep: true })
watch([startDate, endDate], () => load())

function getOrInitChart(elId) {
  const el = document.getElementById(elId)
  if (!el) return null
  if (!chart || chart.getDom() !== el) {
    if (chart) { try { chart.dispose() } catch (e) {} }
    chart = echarts.init(el, null, { renderer: 'canvas' })
  }
  return chart
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

function computeMA(closes, n) {
  if (closes.length < n) return new Array(closes.length).fill(null)
  const out = []
  let sum = 0
  for (let i = 0; i < closes.length; i++) {
    sum += closes[i]
    if (i >= n) sum -= closes[i - n]
    out.push(i >= n - 1 ? sum / n : null)
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
  if (closes.length < n) return out
  for (let i = 0; i < closes.length; i++) {
    if (i < n - 1) {
      out.upper.push(null); out.mid.push(null); out.lower.push(null)
      continue
    }
    const slice = closes.slice(i - n + 1, i + 1)
    const mean = slice.reduce((a, b) => a + b, 0) / n
    const variance = slice.reduce((a, b) => a + (b - mean) ** 2, 0) / n
    const sd = Math.sqrt(variance)
    out.mid.push(mean)
    out.upper.push(mean + k * sd)
    out.lower.push(mean - k * sd)
  }
  return out
}

function drawChart() {
  if (!data.value?.kline?.length) return
  const c = getOrInitChart('kline-chart')
  if (!c) return
  const dates = data.value.kline.map(k => k.date)
  const kline = data.value.kline
  const closes = kline.map(k => k.close)
  const kValues = kline.map((k, i) => [i, k.open, k.close, k.low, k.high])

  // 主图区(蜡烛 + MA + BOLL) + 副图区(成交量)
  const grid = visibleIndicators.value.volume
    ? [
        { left: 60, right: 30, top: 60, height: '60%' },
        { left: 60, right: 30, top: '76%', height: '16%' },
      ]
    : [{ left: 60, right: 30, top: 60, height: '78%' }]

  const xAxis = visibleIndicators.value.volume
    ? [
        { type: 'category', data: dates, gridIndex: 0, axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' } },
        { type: 'category', data: dates, gridIndex: 1, axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { show: false } },
      ]
    : [{ type: 'category', data: dates, axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' } }]

  const series = [{
    name: 'K线', type: 'candlestick', data: kValues,
    xAxisIndex: 0, yAxisIndex: 0,
    itemStyle: {
      color: '#02c076', color0: '#f6465d',
      borderColor: '#02c076', borderColor0: '#f6465d'
    }
  }]

  // 多条 MA
  const MA_COLORS = {
    ma5: '#9b59b6', ma7: '#3498db', ma10: '#e67e22', ma20: '#f1c40f',
    ma25: '#f0b90b', ma60: '#e74c3c', ma99: '#1abc9c',
  }
  for (const k of ['ma5', 'ma7', 'ma10', 'ma20', 'ma25', 'ma60', 'ma99']) {
    if (!visibleIndicators.value[k]) continue
    const ma = computeMA(closes, parseInt(k.slice(2)))
    series.push({
      name: k.toUpperCase(), type: 'line', data: ma, smooth: true, showSymbol: false,
      xAxisIndex: 0, yAxisIndex: 0,
      lineStyle: { width: 1.2, color: MA_COLORS[k] }
    })
  }
  // EMA20
  if (visibleIndicators.value.ema) {
    const ema = computeEMA(closes, 20)
    series.push({
      name: 'EMA20', type: 'line', data: ema, smooth: true, showSymbol: false,
      xAxisIndex: 0, yAxisIndex: 0,
      lineStyle: { width: 1.2, color: '#16a085', type: 'dashed' }
    })
  }
  // BOLL
  if (visibleIndicators.value.boll) {
    const b = computeBOLL(closes, 20, 2)
    series.push({ name: 'BOLL上轨', type: 'line', data: b.upper, smooth: true, showSymbol: false,
      xAxisIndex: 0, yAxisIndex: 0,
      lineStyle: { width: 0.8, color: '#8e44ad', opacity: 0.6 } })
    series.push({ name: 'BOLL中轨', type: 'line', data: b.mid, smooth: true, showSymbol: false,
      xAxisIndex: 0, yAxisIndex: 0,
      lineStyle: { width: 0.8, color: '#8e44ad', opacity: 0.6 } })
    series.push({ name: 'BOLL下轨', type: 'line', data: b.lower, smooth: true, showSymbol: false,
      xAxisIndex: 0, yAxisIndex: 0,
      lineStyle: { width: 0.8, color: '#8e44ad', opacity: 0.6 } })
  }
  // 成交量副图
  if (visibleIndicators.value.volume) {
    series.push({
      name: '成交量', type: 'bar', data: kline.map((k, i) => ({
        value: i,
        itemStyle: { color: k.close >= k.open ? 'rgba(2,192,118,0.6)' : 'rgba(246,70,93,0.6)' }
      })),
      xAxisIndex: 1, yAxisIndex: 1,
    })
    // 修正: 成交量要用真实值
    series[series.length - 1].data = kline.map((k, i) => k.volume || 0)
  }

  const yAxis = visibleIndicators.value.volume
    ? [
        { scale: true, axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' }, splitLine: { lineStyle: { color: '#2b3139' } } },
        { scale: true, axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6', fontSize: 10 }, splitLine: { show: false } },
      ]
    : [{ scale: true, axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' }, splitLine: { lineStyle: { color: '#2b3139' } } }]

  const dataZoom = visibleIndicators.value.volume
    ? [
        { type: 'inside', xAxisIndex: [0, 1] },
        { type: 'slider', xAxisIndex: [0, 1], height: 20, bottom: 10, backgroundColor: '#181a20' },
      ]
    : [
        { type: 'inside', xAxisIndex: 0 },
        { type: 'slider', xAxisIndex: 0, height: 20, bottom: 10, backgroundColor: '#181a20' },
      ]

  c.setOption({
    backgroundColor: 'transparent',
    title: { text: `${symbol.value} · ${curInfo.value.name_zh || ''} (${timeframe.value})`,
      left: 'center', top: 10, textStyle: { color: '#eaecef', fontSize: 14 } },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross', link: visibleIndicators.value.volume ? { xAxisIndex: 'all' } : undefined },
      backgroundColor: '#181a20', borderColor: '#474d57', textStyle: { color: '#eaecef' },
      formatter: (params) => {
        if (!params || !params.length) return ''
        const candle = params.find(p => p.seriesType === 'candlestick')
        if (!candle) return params.map(p => `${p.marker} ${p.seriesName}: ${p.value}`).join('<br/>')
        const o = candle.data[1], c = candle.data[2], h = candle.data[4], l = candle.data[3]
        const chg = c - o
        const chgPct = (chg / o * 100).toFixed(2)
        const color = chg >= 0 ? '#02c076' : '#f6465d'
        let html = `<b>${candle.axisValueLabel}</b><br/>`
        html += `开盘 <b>${o.toFixed(2)}</b>　<span style="color:${color}">${chgPct}%</span><br/>`
        html += `收盘 <b>${c.toFixed(2)}</b><br/>`
        html += `最高 <b style="color:#02c076">${h.toFixed(2)}</b>　最低 <b style="color:#f6465d">${l.toFixed(2)}</b><br/>`
        for (const p of params) {
          if (p.seriesType === 'candlestick') continue
          if (p.value == null) continue
          html += `${p.marker} ${p.seriesName}: <b>${typeof p.value === 'number' ? p.value.toFixed(2) : p.value}</b><br/>`
        }
        return html
      }
    },
    legend: { data: series.map(s => s.name), top: 36, textStyle: { color: '#b7bdc6' } },
    grid, xAxis, yAxis, series, dataZoom,
  })
}

function onResize() { chart?.resize() }
window.addEventListener('resize', onResize)
onUnmounted(() => window.removeEventListener('resize', onResize))

function fmt(v, d = 2) { return v === null || v === undefined ? '-' : Number(v).toFixed(d) }
function fmtPct(v) { return v === null || v === undefined ? '-' : (v * 100).toFixed(2) + '%' }
</script>

<template>
  <div class="kline-view">
    <div class="info-card" v-if="curInfo.symbol">
      <div class="info-header">
        <div>
          <h2>
            {{ curInfo.name_zh }}
            <span class="en">({{ curInfo.name_en }} · {{ curInfo.symbol }})</span>
          </h2>
          <div class="meta">
            <span class="badge">{{ curInfo.category }}</span>
            <span class="badge rank">市值 #{{ curInfo.market_cap_rank }}</span>
            <span v-for="t in curInfo.tags" :key="t" class="tag">#{{ t }}</span>
          </div>
        </div>
      </div>
      <p class="desc">{{ curInfo.description }}</p>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <select v-model="symbol">
          <option v-for="s in allSymbols" :key="s" :value="s">
            {{ s }} {{ symbolInfo[s]?.name_zh || '' }}
          </option>
        </select>
        <TimeframePicker v-model="timeframe" />
        <DateRangePicker v-model:start="startDate" v-model:end="endDate" default-range="3m" />
      </div>
      <div class="toolbar-right">
        <span v-if="loading" class="loading-spinner">⏳ 加载中...</span>
        <button class="refresh-btn" @click="load" :disabled="loading" :title="loading ? '加载中...' : '刷新数据'">
          🔄 {{ loading ? '加载中' : '刷新' }}
        </button>
        <button :class="{ active: tableView === 'chart' }" @click="tableView = 'chart'">K线图</button>
        <button :class="{ active: tableView === 'table' }" @click="tableView = 'table'">数据表</button>
      </div>
    </div>

    <div class="stats-row" v-if="stats.rows">
      <div class="stat"><span class="lbl">数据点</span><span class="val">{{ stats.rows }}</span></div>
      <div class="stat"><span class="lbl">区间</span><span class="val small">{{ stats.start }} → {{ stats.end }}</span></div>
      <div class="stat"><span class="lbl">首日</span><span class="val">{{ fmt(stats.first_close) }}</span></div>
      <div class="stat"><span class="lbl">最新</span><span class="val">{{ fmt(stats.last_close) }}</span></div>
      <div class="stat"><span class="lbl">区间涨跌</span>
        <span class="val" :class="stats.period_return >= 0 ? 'pos' : 'neg'">{{ fmtPct(stats.period_return) }}</span>
      </div>
      <div class="stat"><span class="lbl">最高</span><span class="val">{{ fmt(stats.max_price) }}</span></div>
      <div class="stat"><span class="lbl">最低</span><span class="val">{{ fmt(stats.min_price) }}</span></div>
    </div>

    <div v-if="tableView === 'chart'" class="chart-area">
      <div class="indicator-toggles">
        <span class="lbl">均线</span>
        <label><input type="checkbox" v-model="visibleIndicators.ma5" /> MA5</label>
        <label><input type="checkbox" v-model="visibleIndicators.ma7" /> MA7</label>
        <label><input type="checkbox" v-model="visibleIndicators.ma10" /> MA10</label>
        <label><input type="checkbox" v-model="visibleIndicators.ma20" /> MA20</label>
        <label><input type="checkbox" v-model="visibleIndicators.ma25" /> MA25</label>
        <label><input type="checkbox" v-model="visibleIndicators.ma60" /> MA60</label>
        <label><input type="checkbox" v-model="visibleIndicators.ma99" /> MA99</label>
        <label><input type="checkbox" v-model="visibleIndicators.ema" /> EMA20</label>
        <span class="sep">|</span>
        <label><input type="checkbox" v-model="visibleIndicators.boll" /> BOLL</label>
        <span class="sep">|</span>
        <label><input type="checkbox" v-model="visibleIndicators.volume" /> 成交量</label>
      </div>
      <div class="chart-wrap" :class="{ loading: loading }">
        <div id="kline-chart"></div>
        <div v-if="loading" class="chart-overlay">
          <div class="spinner"></div>
          <span>正在获取 K 线数据...</span>
        </div>
      </div>
    </div>

    <div v-else class="table-area">
      <table>
        <thead>
          <tr>
            <th>时间</th><th>开</th><th>高</th><th>低</th><th>收</th>
            <th>MA7</th><th>MA25</th><th>MA99</th><th>成交量</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in tableRows" :key="r.date">
            <td>{{ r.date }}</td>
            <td>{{ fmt(r.open) }}</td>
            <td>{{ fmt(r.high) }}</td>
            <td>{{ fmt(r.low) }}</td>
            <td :class="r.close > r.open ? 'pos' : 'neg'">{{ fmt(r.close) }}</td>
            <td>{{ fmt(r.ma7) }}</td>
            <td>{{ fmt(r.ma25) }}</td>
            <td>{{ fmt(r.ma99) }}</td>
            <td>{{ Math.round(r.volume).toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <StateView :loading="loading" :error="error" empty-text="请选择币种" empty-icon="📊" v-if="!data && !loading && !error" />
  </div>
</template>

<style scoped>
.kline-view { display: flex; flex-direction: column; gap: 16px; }
.info-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px 24px;
}
.info-header { margin-bottom: 12px; }
.info-header h2 { font-size: 24px; color: var(--yellow); }
.info-header .en { font-size: 14px; color: var(--text-secondary); font-weight: 400; margin-left: 8px; }
.meta { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.badge {
  background: rgba(240,185,11,0.15);
  color: var(--yellow);
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-family: 'Consolas', monospace;
  border: 1px solid rgba(240,185,11,0.3);
}
.tag {
  background: var(--bg);
  color: var(--text-secondary);
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 11px;
}
.desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  white-space: pre-line;
}
.toolbar {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
.toolbar select, .toolbar input {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.toolbar input { width: 110px; }
.toolbar button {
  background: var(--bg-elevated);
  color: var(--text);
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
}
.toolbar button.active { background: var(--yellow); color: #000; font-weight: 600; }
.stats-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 10px;
}
.stat {
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 10px 12px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stat .lbl { font-size: 11px; color: var(--text-secondary); }
.stat .val { font-size: 14px; font-weight: 600; font-family: 'Consolas', monospace; }
.stat .val.small { font-size: 11px; }
.val.pos { color: var(--green); }
.val.neg { color: var(--red); }
.chart-area {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
}
.ma-toggles {
  display: flex;
  gap: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}
.indicator-toggles {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}
.indicator-toggles .lbl {
  color: var(--text-secondary);
  font-weight: 600;
  margin-right: 4px;
}
.indicator-toggles .sep {
  color: var(--border);
  margin: 0 2px;
}
.indicator-toggles label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}
.indicator-toggles label:hover { color: var(--text); }
.indicator-toggles input[type="checkbox"] { accent-color: var(--yellow); }
#kline-chart { height: 500px; }
.chart-wrap { position: relative; }
.chart-wrap.loading { opacity: 0.5; transition: opacity 0.2s; }
.chart-overlay {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px;
  color: var(--yellow);
  font-size: 13px;
  pointer-events: none;
}
.spinner {
  width: 32px; height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--yellow);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-spinner { color: var(--yellow); font-size: 12px; }
.refresh-btn {
  background: var(--bg-elevated);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
}
.refresh-btn:hover:not(:disabled) { border-color: var(--yellow); color: var(--yellow); }
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.table-area {
  max-height: 600px;
  overflow: auto;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
}
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left;
  padding: 10px 12px;
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 1;
}
td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
tr:hover td { background: var(--bg-elevated); }
.pos { color: var(--green); }
.neg { color: var(--red); }
</style>