<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { scanPool } from '../api'
import * as echarts from 'echarts'

import MetricCard from '../components/MetricCard.vue'
import StrategyPicker from '../components/StrategyPicker.vue'
import TimeframePicker from '../components/TimeframePicker.vue'

const props = defineProps({ cfg: Object, reload: Function })

const symbolInfo = computed(() => {
  const m = {}
  for (const s of props.cfg?.symbols || []) m[s.symbol] = s
  return m
})

const params = ref({
  strategy: 'ma_cross',
  timeframe: '4h',
  symbols: [],
  ma_short: 7, ma_long: 25,
  top_n: 3, hold: 12, lookback: 24,
  rsi_period: 14, rsi_oversold: 30, rsi_overbought: 70,
  macd_fast: 12, macd_slow: 26, macd_signal: 9,
  initial_capital: 10000, commission: 0.0004, leverage: 1,
  start_date: '20240101', end_date: '20250601',
})

watch(() => props.cfg, (v) => {
  if (!v) return
  params.value.strategy = 'ma_cross'
  params.value.timeframe = v.settings.backtest.default_timeframe
  params.value.symbols = [...v.settings.active_symbols]
  params.value.initial_capital = v.settings.backtest.initial_capital
  params.value.commission = v.settings.backtest.commission
  params.value.start_date = v.settings.backtest.start_date
  params.value.end_date = v.settings.backtest.end_date === 'auto'
    ? new Date().toISOString().slice(0, 10).replace(/-/g, '') : v.settings.backtest.end_date
  params.value.leverage = v.settings.backtest.leverage
  Object.assign(params.value, v.settings.strategy_defaults[v.settings.strategy] || {})
}, { immediate: true })

watch(() => params.value.strategy, (sid) => {
  const def = props.cfg?.settings?.strategy_defaults?.[sid]
  if (def) Object.assign(params.value, def)
})

const result = ref(null)
const loading = ref(false)
const error = ref('')
const sortKey = ref('sharpe')
const sortDir = ref('desc')
let chart = null

const strategies = computed(() => props.cfg?.strategies || [])
const timeframes = computed(() => props.cfg?.settings?.timeframes || [])
const activeStrategy = computed(() => strategies.value.find(s => s.id === params.value.strategy))
const activeParamsSchema = computed(() => activeStrategy.value?.params_schema || {})

const STRATEGY_FIELDS = {
  ma_cross: ['ma_short', 'ma_long'],
  momentum_rotation: ['top_n', 'hold', 'lookback'],
  rsi: ['rsi_period', 'rsi_oversold', 'rsi_overbought'],
  macd: ['macd_fast', 'macd_slow', 'macd_signal'],
}

function fmtPct(v) { return v === null || v === undefined ? '-' : (v * 100).toFixed(2) + '%' }
function fmtNum(v, d = 2) { return v === null || v === undefined ? '-' : Number(v).toFixed(d) }
function sortBy(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  else { sortKey.value = key; sortDir.value = 'desc' }
}

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

const strategyDesc = computed(() => activeStrategy.value?.description || '')

onMounted(() => run())

async function run() {
  if (!params.value.symbols.length) {
    error.value = '请先在「配置中心」添加至少一个币种'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await scanPool(params.value)
    result.value = res.data
    await nextTick()
    drawChart()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function drawChart() {
  if (!result.value?.combined_equity?.length) return
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
    series.push({ name: 'BTC', type: 'line', data: bm, smooth: true, showSymbol: false,
      lineStyle: { width: 1.5, color: '#f7931a' } })
  }
  chart.setOption({
    backgroundColor: 'transparent',
    title: { text: `币池组合 (${result.value.count} 个币种 · ${result.value.timeframe})`,
      left: 'center', textStyle: { color: '#eaecef', fontSize: 14 } },
    tooltip: { trigger: 'axis', backgroundColor: '#181a20', borderColor: '#2b3139',
      textStyle: { color: '#eaecef' }, valueFormatter: v => (v * 100).toFixed(2) + '%' },
    legend: { data: ['组合策略', 'BTC'], top: 30, textStyle: { color: '#b7bdc6' } },
    grid: { left: 60, right: 30, top: 80, bottom: 60 },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#474d57' } },
      axisLabel: { color: '#b7bdc6', formatter: v => (v * 100).toFixed(0) + '%' },
      splitLine: { lineStyle: { color: '#2b3139' } } },
    series,
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 10, backgroundColor: '#181a20' }]
  })
}

window.addEventListener('resize', () => chart?.resize())
</script>

<template>
  <div class="dashboard">
    <div class="top-bar">
      <StrategyPicker :strategies="strategies" v-model="params.strategy" @change="run" />
      <TimeframePicker :timeframes="timeframes" v-model="params.timeframe" @change="run" />
      <button class="run-btn" :disabled="loading" @click="run">
        {{ loading ? '运行中...' : '重新扫描' }}
      </button>
    </div>

    <div class="config-row">
      <div v-for="key in (STRATEGY_FIELDS[params.strategy] || [])" :key="key" class="cfg">
        <label>{{ activeParamsSchema[key]?.label || key }}</label>
        <input type="number" v-model.number="params[key]"
          :min="activeParamsSchema[key]?.min"
          :max="activeParamsSchema[key]?.max"
          @change="run" />
      </div>
      <div class="cfg">
        <label>杠杆</label>
        <select v-model.number="params.leverage" @change="run">
          <option v-for="x in [1,2,3,5,10]" :key="x" :value="x">{{ x }}x</option>
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
        <label>资金</label>
        <input type="number" v-model.number="params.initial_capital" step="1000" @change="run" />
      </div>
      <div class="cfg">
        <label>费率</label>
        <input type="number" v-model.number="params.commission" step="0.0001" @change="run" />
      </div>

      <div class="desc-box">
        <span>💡</span>
        <span>{{ strategyDesc }}</span>
      </div>
    </div>

    <div v-if="error" class="error">⚠️ {{ error }}</div>

    <div class="metrics-grid" v-if="metrics && Object.keys(metrics).length">
      <MetricCard label="总收益" :value="metrics.total_return" highlight />
      <MetricCard label="年化" :value="metrics.annual_return" />
      <MetricCard label="夏普" :value="metrics.sharpe" highlight fmt="num" />
      <MetricCard label="最大回撤" :value="metrics.max_drawdown" />
      <MetricCard label="BTC 同期" :value="metrics.benchmark_return" />
      <MetricCard label="超额收益" :value="metrics.excess_return" highlight />
      <MetricCard label="胜率" :value="metrics.win_rate" />
      <MetricCard label="信息比率" :value="metrics.information_ratio" fmt="num" />
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
            <th>名称</th>
            <th class="sortable" @click="sortBy('total_return')">
              总收益 {{ sortKey==='total_return' ? (sortDir==='desc'?'↓':'↑') : '' }}
            </th>
            <th class="sortable" @click="sortBy('annual_return')">
              年化 {{ sortKey==='annual_return' ? (sortDir==='desc'?'↓':'↑') : '' }}
            </th>
            <th class="sortable" @click="sortBy('sharpe')">
              夏普 {{ sortKey==='sharpe' ? (sortDir==='desc'?'↓':'↑') : '' }}
            </th>
            <th class="sortable" @click="sortBy('calmar')">
              Calmar {{ sortKey==='calmar' ? (sortDir==='desc'?'↓':'↑') : '' }}
            </th>
            <th class="sortable" @click="sortBy('max_drawdown')">
              回撤 {{ sortKey==='max_drawdown' ? (sortDir==='desc'?'↓':'↑') : '' }}
            </th>
            <th class="sortable" @click="sortBy('win_rate')">
              胜率 {{ sortKey==='win_rate' ? (sortDir==='desc'?'↓':'↑') : '' }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in ranking" :key="r.symbol" :class="{ top: i < 3 }">
            <td class="rank">
              <span v-if="i === 0">🥇</span>
              <span v-else-if="i === 1">🥈</span>
              <span v-else-if="i === 2">🥉</span>
              <span v-else>{{ i + 1 }}</span>
            </td>
            <td class="sym-cell">{{ r.symbol }}</td>
            <td class="name-cell">{{ symbolInfo[r.symbol]?.name_zh || '—' }}</td>
            <td :class="r.total_return >= 0 ? 'pos' : 'neg'">{{ fmtPct(r.total_return) }}</td>
            <td :class="r.annual_return >= 0 ? 'pos' : 'neg'">{{ fmtPct(r.annual_return) }}</td>
            <td :class="r.sharpe >= 1 ? 'pos' : r.sharpe < 0 ? 'neg' : ''">{{ fmtNum(r.sharpe) }}</td>
            <td :class="r.calmar >= 1 ? 'pos' : ''">{{ fmtNum(r.calmar) }}</td>
            <td class="neg">{{ fmtPct(r.max_drawdown) }}</td>
            <td>{{ fmtPct(r.win_rate) }}</td>
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
  gap: 10px;
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
  font-size: 13px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 10px;
}

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
  font-size: 11px;
  font-weight: 500;
  border-bottom: 1px solid var(--binance-border);
  user-select: none;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
th.sortable { cursor: pointer; }
th.sortable:hover { color: var(--binance-yellow); }
td {
  padding: 10px 12px;
  border-bottom: 1px solid #2b3139;
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
tr.top { background: #f0b90b08; }
tr:hover td { background: #181a20; }
.rank { font-size: 16px; }
.sym-cell { font-weight: 600; color: var(--binance-yellow); }
.name-cell { color: var(--binance-text-secondary); font-family: inherit; font-size: 12px; }
.pos { color: var(--binance-green); }
.neg { color: var(--binance-red); }

@media (max-width: 1280px) {
  .metrics-grid { grid-template-columns: repeat(4, 1fr); }
}
</style>