<script setup>
import { ref, computed, watch, nextTick, inject } from 'vue'
import { getKline } from '../api'
import * as echarts from 'echarts'

import TimeframePicker from '../components/TimeframePicker.vue'
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
const visibleMA = ref({ ma7: true, ma25: true, ma99: false })
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

watch([symbol, timeframe], () => load())
watch(visibleMA, () => drawChart(), { deep: true })

async function load() {
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

function drawChart() {
  if (!data.value?.kline?.length) return
  const el = document.getElementById('kline-chart')
  if (!el) return
  if (!chart) chart = echarts.init(el, null, { renderer: 'canvas' })
  const dates = data.value.kline.map(k => k.date)
  const kValues = data.value.kline.map((k, i) => [i, k.open, k.close, k.low, k.high])
  const series = [{
    name: 'K线', type: 'candlestick', data: kValues,
    itemStyle: { color: '#02c076', color0: '#f6465d', borderColor: '#02c076', borderColor0: '#f6465d' }
  }]
  for (const k of ['ma7', 'ma25', 'ma99']) {
    if (!visibleMA.value[k]) continue
    series.push({
      name: k.toUpperCase(), type: 'line',
      data: data.value.kline.map((row, i) => row[k] ? [i, row[k]] : null),
      smooth: true, showSymbol: false, lineStyle: { width: 1.2 }
    })
  }
  chart.setOption({
    backgroundColor: 'transparent',
    title: { text: `${symbol.value} · ${curInfo.value.name_zh || ''} (${timeframe.value})`,
      left: 'center', textStyle: { color: '#eaecef', fontSize: 14 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' },
      backgroundColor: '#181a20', borderColor: '#474d57', textStyle: { color: '#eaecef' } },
    legend: { data: ['K线', 'MA7', 'MA25', 'MA99'], top: 30, textStyle: { color: '#b7bdc6' } },
    grid: { left: 60, right: 30, top: 80, bottom: 60 },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' } },
    yAxis: { scale: true, axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' }, splitLine: { lineStyle: { color: '#2b3139' } } },
    dataZoom: [{ type: 'inside', xAxisIndex: 0 }, { type: 'slider', xAxisIndex: 0, height: 20, bottom: 10, backgroundColor: '#181a20' }],
    series
  })
}

window.addEventListener('resize', () => chart?.resize())

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
        <TimeframePicker :timeframes="timeframes" v-model="timeframe" />
        <input type="text" v-model="startDate" placeholder="开始" />
        <span>→</span>
        <input type="text" v-model="endDate" placeholder="结束" />
      </div>
      <div class="toolbar-right">
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
      <div class="ma-toggles">
        <label><input type="checkbox" v-model="visibleMA.ma7" /> MA7</label>
        <label><input type="checkbox" v-model="visibleMA.ma25" /> MA25</label>
        <label><input type="checkbox" v-model="visibleMA.ma99" /> MA99</label>
      </div>
      <div id="kline-chart"></div>
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
.ma-toggles label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}
#kline-chart { height: 500px; }
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