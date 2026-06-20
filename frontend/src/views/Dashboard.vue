<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { scanPool } from '../api'
import * as echarts from 'echarts'

const props = defineProps({ cfg: Object })

const params = ref({
  strategy: 'ma_cross',
  timeframe: '4h',
  ma_short: 7, ma_long: 25,
  top_n: 3, hold: 12, lookback: 24,
  rsi_period: 14, rsi_oversold: 30, rsi_overbought: 70,
  macd_fast: 12, macd_slow: 26, macd_signal: 9,
  initial_capital: 10000, commission: 0.0004, leverage: 1,
  start_date: '20240101', end_date: '20250601',
})

const result = ref(null)
const loading = ref(false)
const error = ref('')
const sortKey = ref('sharpe')
const sortDir = ref('desc')
let chart = null

watch(() => props.cfg, (v) => {
  if (v?.default_params) {
    Object.assign(params.value, v.default_params)
  }
}, { immediate: true })

const metrics = computed(() => result.value?.combined_metrics || {})
const ranking = computed(() => {
  if (!result.value?.ranking) return []
  const arr = [...result.value.ranking]
  arr.sort((a, b) => {
    const va = a[sortKey.value] ?? -999
    const vb = b[sortKey.value] ?? -999
    return sortDir.value === 'desc' ? vb - va : va - vb
  })
  return arr
})

const strategies = computed(() => props.cfg?.strategies || [])
const timeframes = computed(() => props.cfg?.timeframes || [])
const activeStrategy = computed(() => strategies.value.find(s => s.id === params.value.strategy))

const STRATEGY_FIELDS = {
  ma_cross: [
    { key: 'ma_short', label: '短均线', step: 1 },
    { key: 'ma_long', label: '长均线', step: 1 },
  ],
  momentum_rotation: [
    { key: 'top_n', label: 'Top N', step: 1 },
    { key: 'hold', label: '持仓(根)', step: 1 },
    { key: 'lookback', label: '回看(根)', step: 1 },
  ],
  rsi: [
    { key: 'rsi_period', label: 'RSI 周期', step: 1 },
    { key: 'rsi_oversold', label: '超卖线', step: 1 },
    { key: 'rsi_overbought', label: '超买线', step: 1 },
  ],
  macd: [
    { key: 'macd_fast', label: '快 EMA', step: 1 },
    { key: 'macd_slow', label: '慢 EMA', step: 1 },
    { key: 'macd_signal', label: '信号线', step: 1 },
  ],
}

function fmtPct(v) { return v === null || v === undefined ? '-' : (v * 100).toFixed(2) + '%' }
function fmtNum(v, d = 2) { return v === null || v === undefined ? '-' : Number(v).toFixed(d) }
function sortBy(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
}

onMounted(() => run())

async function run() {
  loading.value = true
  error.value = ''
  try {
    const res = await scanPool(params.value)
    result.value = res.data
    await nextTick()
    drawChart()
  } catch (e) {
    error.value = e?.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

function drawChart() {
  if (!result.value || !result.value.combined_equity?.length) return
  const el = document.getElementById('equity-chart')
  if (!el) return
  if (!chart) chart = echarts.init(el, 'dark')

  const startEq = result.value.combined_equity[0].equity
  const equity = result.value.combined_equity.map(r => [r.date, r.equity / startEq])
  const series = [{
    name: '组合策略', type: 'line', data: equity, smooth: true, showSymbol: false,
    lineStyle: { width: 2.5, color: '#f0b90b' },
    areaStyle: { color: 'rgba(240,185,11,0.08)' }
  }]

  if (result.value.benchmark?.length) {
    const startNav = result.value.benchmark[0].nav
    const bm = result.value.benchmark.map(r => [r.date, r.nav / startNav])
    series.push({
      name: 'BTC', type: 'line', data: bm, smooth: true, showSymbol: false,
      lineStyle: { width: 1.5, color: '#f7931a' }
    })
  }

  chart.setOption({
    backgroundColor: 'transparent',
    title: { text: `币池组合 (${result.value.count} 个币种)`, left: 'center', textStyle: { color: '#eaecef', fontSize: 14 } },
    tooltip: { trigger: 'axis', backgroundColor: '#181a20', borderColor: '#2b3139', textStyle: { color: '#eaecef' }, valueFormatter: v => (v * 100).toFixed(2) + '%' },
    legend: { data: ['组合策略', 'BTC'], top: 30, textStyle: { color: '#b7bdc6' } },
    grid: { left: 60, right: 30, top: 80, bottom: 60 },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6', formatter: v => (v * 100).toFixed(0) + '%' }, splitLine: { lineStyle: { color: '#2b3139' } } },
    series,
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 10, backgroundColor: '#181a20' }]
  })
}

window.addEventListener('resize', () => chart?.resize())

const strategyDesc = computed(() => activeStrategy.value?.desc || '')
</script>

<template>
  <div class="dashboard">
    <div class="top-bar">
      <div class="strategy-pills">
        <button v-for="s in strategies" :key="s.id"
          :class="{ active: params.strategy === s.id }"
          @click="params.strategy = s.id; run()">
          <span class="icon">{{ s.icon }}</span>
          <span class="label">{{ s.name }}</span>
        </button>
      </div>

      <div class="timeframe-pills">
        <span class="lbl">K线</span>
        <button v-for="tf in timeframes" :key="tf"
          :class="{ active: params.timeframe === tf }"
          @click="params.timeframe = tf; run()">{{ tf }}</button>
      </div>

      <button class="run-btn" :disabled="loading" @click="run">
        {{ loading ? '运行中...' : '重新扫描' }}
      </button>
    </div>

    <div class="config-row">
      <div v-for="f in (STRATEGY_FIELDS[params.strategy] || [])" :key="f.key" class="cfg">
        <label>{{ f.label }}</label>
        <input type="number" v-model.number="params[f.key]" :step="f.step" @change="run" />
      </div>

      <div class="cfg">
        <label>杠杆</label>
        <select v-model.number="params.leverage" @change="run">
          <option :value="1">1x</option>
          <option :value="2">2x</option>
          <option :value="3">3x</option>
          <option :value="5">5x</option>
        </select>
      </div>
      <div class="cfg">
        <label>开始</label>
        <input type="text" v-model="params.start_date" @change="run" />
      </div>
      <div class="cfg">
        <label>结束</label>
        <input type="text" v-model="params.end_date" @change="run" />
      </div>
      <div class="cfg">
        <label>初始资金</label>
        <input type="number" v-model.number="params.initial_capital" step="1000" @change="run" />
      </div>

      <div class="desc-box">
        <span>💡</span>
        <span>{{ strategyDesc }}</span>
      </div>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <div class="metrics-grid" v-if="metrics && Object.keys(metrics).length">
      <div class="metric-card highlight">
        <div class="metric-label">总收益</div>
        <div class="metric-value" :class="metrics.total_return >= 0 ? 'pos' : 'neg'">{{ fmtPct(metrics.total_return) }}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">年化收益</div>
        <div class="metric-value" :class="metrics.annual_return >= 0 ? 'pos' : 'neg'">{{ fmtPct(metrics.annual_return) }}</div>
      </div>
      <div class="metric-card highlight">
        <div class="metric-label">夏普</div>
        <div class="metric-value" :class="metrics.sharpe >= 1 ? 'pos' : metrics.sharpe < 0 ? 'neg' : ''">{{ fmtNum(metrics.sharpe) }}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">最大回撤</div>
        <div class="metric-value neg">{{ fmtPct(metrics.max_drawdown) }}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">BTC 同期</div>
        <div class="metric-value">{{ fmtPct(metrics.benchmark_return) }}</div>
      </div>
      <div class="metric-card highlight">
        <div class="metric-label">超额收益</div>
        <div class="metric-value" :class="metrics.excess_return >= 0 ? 'pos' : 'neg'">{{ fmtPct(metrics.excess_return) }}</div>
      </div>
    </div>

    <div id="equity-chart" class="chart"></div>

    <div class="ranking-section">
      <div class="ranking-header">
        <h3>单币表现排名</h3>
        <div class="sort-tip">点击表头切换排序 · 当前 {{ result?.count || 0 }} 个币种</div>
      </div>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>币种</th>
            <th class="sortable" @click="sortBy('total_return')">总收益 {{ sortKey==='total_return' ? (sortDir==='desc'?'↓':'↑') : '' }}</th>
            <th class="sortable" @click="sortBy('annual_return')">年化 {{ sortKey==='annual_return' ? (sortDir==='desc'?'↓':'↑') : '' }}</th>
            <th class="sortable" @click="sortBy('sharpe')">夏普 {{ sortKey==='sharpe' ? (sortDir==='desc'?'↓':'↑') : '' }}</th>
            <th class="sortable" @click="sortBy('max_drawdown')">回撤 {{ sortKey==='max_drawdown' ? (sortDir==='desc'?'↓':'↑') : '' }}</th>
            <th class="sortable" @click="sortBy('annual_volatility')">波动 {{ sortKey==='annual_volatility' ? (sortDir==='desc'?'↓':'↑') : '' }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in ranking" :key="r.symbol" :class="{ top: i < 3 }">
            <td class="rank">
              <span v-if="i === 0" class="medal gold">🥇</span>
              <span v-else-if="i === 1" class="medal silver">🥈</span>
              <span v-else-if="i === 2" class="medal bronze">🥉</span>
              <span v-else>{{ i + 1 }}</span>
            </td>
            <td class="sym-cell">{{ r.symbol }}</td>
            <td :class="r.total_return >= 0 ? 'pos' : 'neg'">{{ fmtPct(r.total_return) }}</td>
            <td :class="r.annual_return >= 0 ? 'pos' : 'neg'">{{ fmtPct(r.annual_return) }}</td>
            <td :class="r.sharpe >= 1 ? 'pos' : r.sharpe < 0 ? 'neg' : ''">{{ fmtNum(r.sharpe) }}</td>
            <td class="neg">{{ fmtPct(r.max_drawdown) }}</td>
            <td>{{ fmtPct(r.annual_volatility) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 16px; }

.top-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  background: var(--binance-card);
  border: 1px solid var(--binance-border);
  border-radius: 12px;
  padding: 14px;
  flex-wrap: wrap;
}
.strategy-pills { display: flex; gap: 6px; flex: 1; }
.strategy-pills button {
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  color: var(--binance-text-secondary);
  padding: 10px 16px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  transition: all 0.2s;
}
.strategy-pills button:hover { border-color: var(--binance-yellow); color: var(--binance-text); }
.strategy-pills button.active {
  background: #f0b90b11;
  border-color: var(--binance-yellow);
  color: var(--binance-yellow);
}
.strategy-pills .icon { font-size: 16px; }

.timeframe-pills {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  border-radius: 8px;
  padding: 4px 8px;
}
.timeframe-pills .lbl { font-size: 11px; color: var(--binance-text-secondary); padding: 0 4px; }
.timeframe-pills button {
  background: transparent;
  color: var(--binance-text-secondary);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
}
.timeframe-pills button.active {
  background: var(--binance-yellow);
  color: #0b0e11;
  font-weight: 600;
}

.run-btn {
  background: var(--binance-yellow);
  color: #0b0e11;
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 700;
}
.run-btn:hover:not(:disabled) { background: #fcd535; }
.run-btn:disabled { opacity: 0.6; }

.config-row {
  display: flex;
  gap: 12px;
  align-items: center;
  background: var(--binance-card);
  border: 1px solid var(--binance-border);
  border-radius: 12px;
  padding: 12px 16px;
  flex-wrap: wrap;
}
.cfg { display: flex; flex-direction: column; gap: 4px; }
.cfg label { font-size: 11px; color: var(--binance-text-secondary); }
.cfg input, .cfg select {
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  color: var(--binance-text);
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  width: 90px;
}
.cfg input:focus, .cfg select:focus { border-color: var(--binance-yellow); }
.desc-box {
  flex: 1;
  background: #1e88e511;
  border: 1px solid #1e88e544;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  color: #64b5f6;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 240px;
}

.error {
  padding: 12px;
  background: #f6465d22;
  border: 1px solid #f6465d;
  border-radius: 8px;
  color: #f6465d;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}
.metric-card {
  background: var(--binance-card);
  border: 1px solid var(--binance-border);
  border-radius: 10px;
  padding: 14px;
}
.metric-card.highlight {
  background: linear-gradient(135deg, #f0b90b11, transparent);
  border-color: #f0b90b44;
}
.metric-label { font-size: 12px; color: var(--binance-text-secondary); margin-bottom: 6px; }
.metric-value {
  font-size: 20px;
  font-weight: 700;
  font-family: 'Consolas', 'Monaco', monospace;
}
.metric-value.pos { color: var(--binance-green); }
.metric-value.neg { color: var(--binance-red); }

.chart {
  height: 360px;
  background: var(--binance-card);
  border: 1px solid var(--binance-border);
  border-radius: 12px;
  padding: 8px;
}

.ranking-section {
  background: var(--binance-card);
  border: 1px solid var(--binance-border);
  border-radius: 12px;
  padding: 20px;
}
.ranking-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.ranking-header h3 { font-size: 16px; }
.sort-tip { font-size: 12px; color: var(--binance-text-secondary); }

table { width: 100%; border-collapse: collapse; }
th {
  text-align: left;
  padding: 10px 12px;
  background: #0b0e11;
  color: var(--binance-text-secondary);
  font-size: 12px;
  font-weight: 500;
  border-bottom: 1px solid var(--binance-border);
  user-select: none;
}
th.sortable { cursor: pointer; }
th.sortable:hover { color: var(--binance-yellow); }
td {
  padding: 10px 12px;
  border-bottom: 1px solid #2b3139;
  font-size: 14px;
  font-family: 'Consolas', monospace;
}
tr.top { background: #f0b90b08; }
tr:hover td { background: #181a20; }
.rank { font-weight: 600; }
.medal { font-size: 18px; }
.sym-cell { font-weight: 600; color: var(--binance-yellow); }
.pos { color: var(--binance-green); }
.neg { color: var(--binance-red); }

@media (max-width: 1280px) {
  .metrics-grid { grid-template-columns: repeat(3, 1fr); }
}
</style>