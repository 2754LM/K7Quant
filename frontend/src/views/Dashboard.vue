<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted, inject } from 'vue'
import { scanPool, runBacktest, backtestCode } from '../api'
import * as echarts from 'echarts'

import MetricCard from '../components/MetricCard.vue'
import StrategyPicker from '../components/StrategyPicker.vue'
import TimeframePicker from '../components/TimeframePicker.vue'
import DateRangePicker from '../components/DateRangePicker.vue'
import StateView from '../components/StateView.vue'
import HelpTip from '../components/HelpTip.vue'

const cfg = inject('cfg')
const reloadCfg = inject('reload')

const mode = ref('preset') // 'preset' | 'code'
const tfMode = ref('single') // 'single' | 'multi'
const multiTfs = ref(['4h', '1d', '1w'])
const multiResults = ref(null)  // 多周期回测结果

// ---------- 预设策略模式 ----------
const params = ref({
  strategy_id: null,
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
  strategies.value.find(s => s.id === params.value.strategy_id)
)

watch(strategies, (list) => {
  if (list.length && params.value.strategy_id === null) {
    params.value.strategy_id = list[0].id
  }
}, { immediate: true })

watch(() => params.value.strategy_id, () => {
  const s = activeStrategy.value
  if (s && s.params_schema) {
    for (const key in s.params_schema) {
      if (s.params_schema[key].default !== undefined && params.value[key] === undefined) {
        params.value[key] = s.params_schema[key].default
      }
    }
  }
  if (mode.value === 'preset') run()
}, { immediate: false })

// ---------- 自定义代码模式 ----------
const codeForm = ref({
  code: 'signal = CROSS_UP(MA(close, 7), MA(close, 25))\n止损 = 0.05\n止盈 = 0.10\n仓位 = 1.0',
  symbol: 'BTCUSDT',
  timeframe: '4h',
  start_date: '20240101',
  end_date: '20250601',
  params: {},
})
const codeResult = ref(null)
const codeLoading = ref(false)
const codeError = ref('')
let codeChart = null

const allSymbols = computed(() => (cfg.value?.symbols || []).map(s => s.symbol))

async function runCode() {
  codeLoading.value = true
  codeError.value = ''
  codeResult.value = null
  try {
    const res = await backtestCode({
      code: codeForm.value.code,
      symbol: codeForm.value.symbol,
      timeframe: codeForm.value.timeframe,
      start_date: codeForm.value.start_date,
      end_date: codeForm.value.end_date,
      params: codeForm.value.params,
    })
    codeResult.value = res.data
    await nextTick()
    drawCodeChart()
  } catch (e) {
    codeError.value = e.message
  } finally {
    codeLoading.value = false
  }
}

function drawCodeChart() {
  if (!codeResult.value?.equity?.length) return
  const el = document.getElementById('code-equity-chart')
  if (!el) return
  if (!codeChart) codeChart = echarts.init(el, null, { renderer: 'canvas' })
  const startEq = codeResult.value.equity[0].equity
  const equity = codeResult.value.equity.map(r => [r.date, r.equity / startEq])
  const series = [{
    name: '策略', type: 'line', data: equity, smooth: true, showSymbol: false,
    lineStyle: { width: 2.5, color: '#f0b90b' },
    areaStyle: { color: 'rgba(240,185,11,0.08)' }
  }]
  if (codeResult.value.benchmark?.length) {
    const b0 = codeResult.value.benchmark[0].nav
    const bm = codeResult.value.benchmark.map(r => [r.date, r.nav / b0])
    series.push({ name: '买入持有', type: 'line', data: bm, smooth: true, showSymbol: false,
      lineStyle: { width: 1.5, color: '#f7931a' } })
  }
  codeChart.setOption({
    backgroundColor: 'transparent',
    title: { text: `${codeForm.value.symbol} · ${codeForm.value.timeframe}`,
      left: 'center', textStyle: { color: '#eaecef', fontSize: 14 } },
    tooltip: { trigger: 'axis', backgroundColor: '#181a20', borderColor: '#2b3139',
      textStyle: { color: '#eaecef' }, valueFormatter: v => (v * 100).toFixed(2) + '%' },
    legend: { data: ['策略', '买入持有'], top: 30, textStyle: { color: '#b7bdc6' } },
    grid: { left: 60, right: 30, top: 80, bottom: 60 },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#474d57' } },
      axisLabel: { color: '#b7bdc6', formatter: v => (v * 100).toFixed(0) + '%' },
      splitLine: { lineStyle: { color: '#2b3139' } } },
    series,
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 10, backgroundColor: '#181a20' }]
  })
}

const codeMetrics = computed(() => {
  const m = codeResult.value?.metrics || {}
  return m
})

// ---------- 共享 ----------
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
  if (tfMode.value === 'multi') {
    if (multiTfs.value.length === 0) {
      error.value = '请至少选择一个周期'
      return
    }
    loading.value = true
    error.value = ''
    multiResults.value = null
    try {
      const results = await Promise.all(multiTfs.value.map(tf =>
        scanPool({ ...params.value, timeframe: tf })
          .then(r => ({ tf, ok: true, data: r.data }))
          .catch(e => ({ tf, ok: false, error: e.message }))
      ))
      multiResults.value = results
      await nextTick()
      drawMultiChart()
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
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

function onResize() { chart?.resize(); codeChart?.resize() }
window.addEventListener('resize', onResize)
onUnmounted(() => window.removeEventListener('resize', onResize))

const MULTI_COLORS = ['#f0b90b', '#3498db', '#e74c3c', '#9b59b6', '#1abc9c', '#e67e22', '#16a085', '#f368e0']

function drawMultiChart() {
  if (!multiResults.value?.length) return
  const el = document.getElementById('equity-chart')
  if (!el) return
  if (!chart) chart = echarts.init(el, null, { renderer: 'canvas' })
  const series = multiResults.value.map((r, i) => {
    if (!r.ok || !r.data?.combined_equity?.length) return null
    const e0 = r.data.combined_equity[0].equity
    const data = r.data.combined_equity.map(rr => [rr.date, rr.equity / e0])
    return {
      name: r.tf, type: 'line', data, smooth: true, showSymbol: false,
      lineStyle: { width: 2, color: MULTI_COLORS[i % MULTI_COLORS.length] }
    }
  }).filter(Boolean)
  chart.setOption({
    backgroundColor: 'transparent',
    title: { text: `多周期对比: ${activeStrategy.value?.name || ''}`, left: 'center',
      textStyle: { color: '#eaecef', fontSize: 14 } },
    tooltip: { trigger: 'axis', backgroundColor: '#181a20', borderColor: '#2b3139',
      textStyle: { color: '#eaecef' }, valueFormatter: v => (v * 100).toFixed(2) + '%' },
    legend: { data: series.map(s => s.name), top: 30, textStyle: { color: '#b7bdc6' } },
    grid: { left: 60, right: 30, top: 80, bottom: 60 },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#474d57' } },
      axisLabel: { color: '#b7bdc6', formatter: v => (v * 100).toFixed(0) + '%' },
      splitLine: { lineStyle: { color: '#2b3139' } } },
    series,
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 10, backgroundColor: '#181a20' }]
  })
}
</script>

<template>
  <div class="dashboard">
    <div class="mode-tabs">
      <button :class="{ active: mode === 'preset' }" @click="mode = 'preset'">📦 预设策略</button>
      <button :class="{ active: mode === 'code' }" @click="mode = 'code'">✏️ 自定义代码</button>
    </div>

    <!-- ========== 预设策略模式 ========== -->
    <template v-if="mode === 'preset'">
      <div class="top-bar">
        <StrategyPicker :strategies="strategies" v-model="params.strategy_id" @change="run" />
        <div class="tf-mode-toggle">
          <button :class="{ active: tfMode === 'single' }" @click="tfMode = 'single'">单周期</button>
          <button :class="{ active: tfMode === 'multi' }" @click="tfMode = 'multi'">多周期对比</button>
        </div>
        <template v-if="tfMode === 'single'">
          <TimeframePicker :timeframes="timeframes" v-model="params.timeframe" @change="run" />
        </template>
        <template v-else>
          <div class="multi-tf">
            <label v-for="tf in timeframes" :key="tf" class="tf-chip">
              <input type="checkbox" :value="tf" v-model="multiTfs" />
              <span>{{ tf }}</span>
            </label>
          </div>
        </template>
        <button class="btn-primary" :disabled="loading" @click="run">
          {{ loading ? '运行中...' : (tfMode === 'multi' ? '▶ 跑多周期' : '重新扫描') }}
        </button>
      </div>

      <div class="config-row">
        <div v-for="(schema, key) in (activeStrategy?.params_schema || {})" :key="key" class="cfg">
          <label>{{ schema.label || key }}</label>
          <input type="number" v-model.number="params[key]"
            :min="schema.min"
            :max="schema.max"
            @change="run" />
        </div>
        <div class="cfg date-cfg">
          <label>区间</label>
          <DateRangePicker v-model:start="params.start_date" v-model:end="params.end_date" default-range="3m" />
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

      <div v-if="!result && !multiResults && !loading && !error" class="empty-state">
        <div class="icon">📈</div>
        <div>选择策略 + K线周期, 自动扫描全池</div>
      </div>

      <div v-if="result || multiResults" id="equity-chart" class="chart"></div>

      <!-- 多周期结果表 -->
      <div v-if="multiResults" class="multi-results card">
        <h3>多周期对比结果</h3>
        <table>
          <thead>
            <tr>
              <th>周期</th>
              <th>状态</th>
              <th>总收益</th>
              <th>年化</th>
              <th>夏普</th>
              <th>最大回撤</th>
              <th>胜率</th>
              <th>币种数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in multiResults" :key="r.tf">
              <td class="tf-name">{{ r.tf }}</td>
              <td v-if="!r.ok" class="neg">✗ {{ r.error }}</td>
              <template v-else>
                <td class="pos">✓</td>
                <td :class="(r.data.combined_metrics?.total_return ?? 0) >= 0 ? 'pos' : 'neg'">{{ fmtPct(r.data.combined_metrics?.total_return) }}</td>
                <td>{{ fmtPct(r.data.combined_metrics?.annual_return) }}</td>
                <td :class="(r.data.combined_metrics?.sharpe ?? 0) >= 1 ? 'pos' : (r.data.combined_metrics?.sharpe ?? 0) < 0 ? 'neg' : ''">{{ fmtNum(r.data.combined_metrics?.sharpe) }}</td>
                <td class="neg">{{ fmtPct(r.data.combined_metrics?.max_drawdown) }}</td>
                <td>{{ fmtPct(r.data.combined_metrics?.win_rate) }}</td>
                <td>{{ r.data.count }}</td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>

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
    </template>

    <!-- ========== 自定义代码模式 ========== -->
    <template v-if="mode === 'code'">
      <div class="code-card">
        <div class="code-header">
          <div class="code-toolbar">
            <div class="form-group">
              <label>币种</label>
              <select v-model="codeForm.symbol">
                <option v-for="s in allSymbols" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>K线</label>
              <TimeframePicker :timeframes="timeframes" v-model="codeForm.timeframe" />
            </div>
            <div class="form-group">
              <label>区间</label>
              <DateRangePicker v-model:start="codeForm.start_date" v-model:end="codeForm.end_date" default-range="3m" />
            </div>
            <button class="btn-primary" :disabled="codeLoading" @click="runCode">
              {{ codeLoading ? '运行中...' : '▶ 运行回测' }}
            </button>
          </div>
        </div>
        <div class="editor-section">
          <label class="editor-label">策略代码 (DSL)</label>
          <textarea v-model="codeForm.code" class="code-input" rows="10"
            placeholder="signal = CROSS_UP(MA(close, 7), MA(close, 25))"></textarea>
          <div class="code-hint">signal = 表达式 (必需) | 止损/止盈/仓位/频率 (可选)</div>
        </div>
      </div>

      <!-- 代码回测结果 -->
      <template v-if="codeResult">
        <div class="metrics-grid">
          <MetricCard label="总收益" :value="codeMetrics.total_return" highlight :help="HELP.total_return" />
          <MetricCard label="年化" :value="codeMetrics.annual_return" :help="HELP.annual_return" />
          <MetricCard label="夏普" :value="codeMetrics.sharpe" highlight fmt="num" :help="HELP.sharpe" />
          <MetricCard label="最大回撤" :value="codeMetrics.max_drawdown" :help="HELP.max_drawdown" />
          <MetricCard label="买入持有" :value="codeMetrics.benchmark_return" />
          <MetricCard label="超额收益" :value="codeMetrics.excess_return" highlight :help="HELP.excess_return" />
          <MetricCard label="胜率" :value="codeMetrics.win_rate" :help="HELP.win_rate" />
          <MetricCard label="交易次数" :value="codeMetrics.trade_count" fmt="num" />
        </div>
        <div id="code-equity-chart" class="chart"></div>

        <div v-if="codeResult.trades?.length" class="trades-section">
          <h3>交易记录 ({{ codeResult.trades.length }})</h3>
          <table>
            <thead>
              <tr>
                <th>时间</th><th>方向</th><th>价格</th><th>数量</th><th>金额</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in codeResult.trades" :key="t.date">
                <td>{{ t.date }}</td>
                <td :class="t.side === 'buy' ? 'pos' : 'neg'">{{ t.side === 'buy' ? '买入' : '卖出' }}</td>
                <td>{{ fmtNum(t.price, 4) }}</td>
                <td>{{ fmtNum(t.amount, 4) }}</td>
                <td>{{ fmtNum(t.cost || t.value, 2) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <StateView :loading="codeLoading" :error="codeError" empty-text="编辑策略代码，点击运行回测" empty-icon="✏️" v-if="!codeResult && !codeLoading && !codeError" />
    </template>
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
.tf-mode-toggle {
  display: flex;
  gap: 2px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 3px 6px;
}
.tf-mode-toggle button {
  background: transparent;
  color: var(--text-secondary);
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
}
.tf-mode-toggle button.active {
  background: var(--yellow);
  color: #000;
  font-weight: 600;
}
.multi-tf {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  align-items: center;
}
.tf-chip {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 4px 10px;
  border-radius: 14px;
  font-size: 11px;
  cursor: pointer;
  user-select: none;
  font-family: 'Consolas', monospace;
}
.tf-chip input { margin-right: 4px; accent-color: var(--yellow); }
.tf-chip:has(input:checked) {
  background: rgba(240,185,11,0.15);
  border-color: var(--yellow);
  color: var(--yellow);
}
.multi-results.card { padding: 16px 20px; }
.multi-results h3 { font-size: 16px; margin-bottom: 12px; }
.multi-results .tf-name { font-weight: 600; color: var(--yellow); font-family: 'Consolas', monospace; }
.date-cfg { min-width: 320px; }
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
.mode-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 8px;
}
.mode-tabs button {
  background: transparent;
  color: var(--text-secondary);
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 13px;
}
.mode-tabs button:hover { background: var(--bg-elevated); }
.mode-tabs button.active { background: var(--yellow); color: #000; font-weight: 600; }

.code-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.code-header { margin-bottom: 16px; }
.code-toolbar {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
}
.code-toolbar .form-group { display: flex; flex-direction: column; gap: 4px; }
.code-toolbar .form-group label { font-size: 11px; color: var(--text-secondary); }
.code-toolbar .form-group input, .code-toolbar .form-group select {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.editor-section { margin-top: 12px; }
.editor-label { font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 6px; }
.code-input {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 12px;
  border-radius: 8px;
  font-size: 13px;
  font-family: 'Consolas', monospace;
  line-height: 1.6;
  resize: vertical;
  box-sizing: border-box;
}
.code-input:focus { border-color: var(--yellow); }
.code-hint { font-size: 11px; color: var(--text-muted); margin-top: 6px; }
.trades-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.trades-section h3 { font-size: 16px; margin-bottom: 12px; }

@media (max-width: 1280px) {
  .metrics-grid { grid-template-columns: repeat(4, 1fr); }
}
</style>