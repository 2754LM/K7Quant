<script setup>
import { ref, computed, watch, nextTick, onMounted, inject, provide } from 'vue'
import { scanPool, runBacktest } from '../api'
import * as echarts from 'echarts'

import MetricCard from '../components/MetricCard.vue'
import StrategyPicker from '../components/StrategyPicker.vue'
import TimeframePicker from '../components/TimeframePicker.vue'
import StateView from '../components/StateView.vue'
import HelpTip from '../components/HelpTip.vue'

const cfg = inject('cfg')
const reloadCfg = inject('reload')

const params = ref({
  strategy_id: 1,
  timeframe: '4h',
  ma_short: 7, ma_long: 25,
  top_n: 3, hold: 12, lookback: 24,
  rsi_period: 14, rsi_oversold: 30, rsi_overbought: 70,
  macd_fast: 12, macd_slow: 26, macd_signal: 9,
  start_date: '20240101', end_date: '20250601',
})

const result = ref(null)
const loading = ref(false)
const error = ref('')
const sortKey = ref('sharpe')
const sortDir = ref('desc')
let chart = null

const strategies = computed(() => cfg.value?.strategies || [])
const timeframes = computed(() => cfg.value?.timeframes || ['1d'])
const activeStrategy = computed(() =>
  strategies.value.find(s => s.id === Number(params.value.strategy_id))
)
const STRATEGY_FIELDS = {
  ma_cross: ['ma_short', 'ma_long'],
  momentum_rotation: ['top_n', 'hold', 'lookback'],
  rsi: ['rsi_period', 'rsi_oversold', 'rsi_overbought'],
  macd: ['macd_fast', 'macd_slow', 'macd_signal'],
}

watch(() => params.value.strategy_id, () => {
  const s = activeStrategy.value
  if (s && s.params_schema) {
    for (const key in s.params_schema) {
      if (s.params_schema[key].default !== undefined && params.value[key] === undefined) {
        params.value[key] = s.params_schema[key].default
      }
    }
  }
  run()
}, { immediate: false })

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

const symbolInfo = computed(() => {
  const m = {}
  for (const s of cfg.value?.symbols || []) m[s.symbol] = s
  return m
})

function fmtPct(v) { return v === null || v === undefined ? '-' : (v * 100).toFixed(2) + '%' }
function fmtNum(v, d = 2) { return v === null || v === undefined ? '-' : Number(v).toFixed(d) }
function sortBy(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  else { sortKey.value = key; sortDir.value = 'desc' }
}

const HELP = {
  total_return: '回测期间的总收益率。>= 0 赚钱, < 0 亏钱。',
  annual_return: '折算到一年的收益率。不同周期的策略可比。',
  sharpe: '每承担一单位风险换多少收益。> 1 不错, > 2 优秀, < 0 别碰。',
  max_drawdown: '从最高点跌下来的最大幅度。< 20% 可接受, > 30% 心理压力大。',
  win_rate: '赚钱的 K 线占比。高不等于赚, 还要看盈亏比。',
  excess_return: '相对 BTC 的超额收益。> 0 表示跑赢 BTC。',
  information_ratio: '超额收益的稳定性。> 0.5 为正, > 1 优秀。',
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
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function drawChart() {
  if (!result.value?.combined_equity?.length) return
  const el = document.getElementById('equity-chart')
  if (!el) return
  if (!chart) chart = echarts.init(el, null, { renderer: 'canvas' })
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
      <StrategyPicker :strategies="strategies" v-model="params.strategy_id" @change="run" />
      <TimeframePicker :timeframes="timeframes" v-model="params.timeframe" @change="run" />
      <button class="btn-primary" :disabled="loading" @click="run">
        {{ loading ? '运行中...' : '重新扫描' }}
      </button>
    </div>

    <div class="config-row">
      <div v-for="key in (STRATEGY_FIELDS[activeStrategy?.id] || [])" :key="key" class="cfg">
        <label>{{ activeStrategy?.params_schema?.[key]?.label || key }}</label>
        <input type="number" v-model.number="params[key]"
          :min="activeStrategy?.params_schema?.[key]?.min"
          :max="activeStrategy?.params_schema?.[key]?.max"
          @change="run" />
      </div>
      <div class="cfg">
        <label>开始</label>
        <input type="text" v-model="params.start_date" @change="run" />
      </div>
      <div class="cfg">
        <label>结束</label>
        <input type="text" v-model="params.end_date" @change="run" />
      </div>
      <div v-if="activeStrategy?.description" class="desc-box">
        <span>💡</span>
        <span>{{ activeStrategy.description }}</span>
      </div>
    </div>

    <div class="metrics-grid" v-if="result">
      <MetricCard label="总收益" :value="metrics.total_return" highlight :help="HELP.total_return" />
      <MetricCard label="年化" :value="metrics.annual_return" :help="HELP.annual_return" />
      <MetricCard label="夏普" :value="metrics.sharpe" highlight fmt="num" :help="HELP.sharpe" />
      <MetricCard label="最大回撤" :value="metrics.max_drawdown" :help="HELP.max_drawdown" />
      <MetricCard label="BTC 同期" :value="metrics.benchmark_return" />
      <MetricCard label="超额收益" :value="metrics.excess_return" highlight :help="HELP.excess_return" />
      <MetricCard label="胜率" :value="metrics.win_rate" :help="HELP.win_rate" />
      <MetricCard label="信息比率" :value="metrics.information_ratio" fmt="num" :help="HELP.information_ratio" />
    </div>

    <div v-if="!result && !loading && !error" class="empty-state">
      <div class="icon">📈</div>
      <div>选择策略 + K线周期, 自动扫描全池</div>
    </div>

    <div v-if="result" id="equity-chart" class="chart"></div>

    <div v-if="result" class="ranking-section">
      <div class="ranking-header">
        <h3>单币表现排名 ({{ result.count }})</h3>
        <div class="sort-tip">点击表头切换排序</div>
      </div>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>币种</th>
            <th>名称</th>
            <th class="sortable" @click="sortBy('total_return')">总收益 {{ sortKey==='total_return' ? (sortDir==='desc'?'↓':'↑') : '' }}</th>
            <th class="sortable" @click="sortBy('sharpe')">夏普 {{ sortKey==='sharpe' ? (sortDir==='desc'?'↓':'↑') : '' }}</th>
            <th class="sortable" @click="sortBy('calmar')">Calmar</th>
            <th class="sortable" @click="sortBy('max_drawdown')">回撤</th>
            <th class="sortable" @click="sortBy('win_rate')">胜率</th>
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
            <td :class="r.sharpe >= 1 ? 'pos' : r.sharpe < 0 ? 'neg' : ''">{{ fmtNum(r.sharpe) }}</td>
            <td :class="r.calmar >= 1 ? 'pos' : ''">{{ fmtNum(r.calmar) }}</td>
            <td class="neg">{{ fmtPct(r.max_drawdown) }}</td>
            <td>{{ fmtPct(r.win_rate) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <StateView :loading="loading" :error="error" />
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 16px; }
.top-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  flex-wrap: wrap;
}
.config-row {
  display: flex;
  gap: 10px;
  align-items: center;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 16px;
  flex-wrap: wrap;
}
.cfg { display: flex; flex-direction: column; gap: 4px; }
.cfg label { font-size: 11px; color: var(--text-secondary); }
.cfg input {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  width: 80px;
}
.cfg input:focus { border-color: var(--yellow); }
.desc-box {
  flex: 1;
  background: rgba(30,136,229,0.08);
  border: 1px solid rgba(30,136,229,0.3);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  color: #64b5f6;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 240px;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 10px;
}
.chart {
  height: 360px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 8px;
}
.ranking-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
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
.sort-tip { font-size: 12px; color: var(--text-secondary); }
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left;
  padding: 10px 12px;
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  border-bottom: 1px solid var(--border);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
th.sortable { cursor: pointer; }
th.sortable:hover { color: var(--yellow); }
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
tr.top { background: rgba(240,185,11,0.04); }
tr:hover td { background: var(--bg-elevated); }
.rank { font-size: 16px; }
.sym-cell { font-weight: 600; color: var(--yellow); }
.name-cell { color: var(--text-secondary); font-family: inherit; font-size: 12px; }
.pos { color: var(--green); }
.neg { color: var(--red); }
@media (max-width: 1280px) {
  .metrics-grid { grid-template-columns: repeat(4, 1fr); }
}
</style>