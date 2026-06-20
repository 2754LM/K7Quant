<script setup>
import { ref, computed, watch, nextTick, inject } from 'vue'
import { computeFactor, computeFactors, correlateFactors, rankFactors, listFactors } from '../api'
import * as echarts from 'echarts'

import StateView from '../components/StateView.vue'
import HelpTip from '../components/HelpTip.vue'

const factorList = ref({ categories: [], factors: [] })
const selectedFactor = ref(null)
const params = ref({ period: 20 })
const symbol = ref('BTCUSDT')
const timeframe = ref('4h')
const start = ref('20240101')
const end = ref('20250601')

const singleResult = ref(null)
const loading = ref(false)
const error = ref('')

const rankResult = ref(null)
const rankLoading = ref(false)

const corrResult = ref(null)
const corrLoading = ref(false)
const corrFactors = ref([])
const corrFactorsStr = ref('rsi,macd_hist,obv')
const corrPeriod = ref(60)

watch(corrFactorsStr, (v) => {
  corrFactors.value = v.split(/[,\s]+/).filter(Boolean)
})

const allSymbols = computed(() => {
  const arr = []
  for (const s of (factorList.value.factors || [])) {
    if (!arr.includes(s.symbol)) arr.push(s.symbol)
  }
  return arr.slice(0, 25)
})

async function loadFactorList() {
  const res = await listFactors()
  factorList.value = res.data
  if (res.data.factors.length && !selectedFactor.value) {
    selectedFactor.value = res.data.factors[0]
  }
}

watch(selectedFactor, (f) => {
  if (f) {
    params.value = {}
    for (const k in f.params_schema) {
      params.value[k] = f.params_schema[k].default
    }
  }
})

async function compute() {
  if (!selectedFactor.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await computeFactor({
      symbol: symbol.value, factor_id: selectedFactor.value.id,
      params: params.value, timeframe: timeframe.value,
      start: start.value, end: end.value,
    })
    if (res.data.error) {
      error.value = res.data.error
      singleResult.value = null
    } else {
      singleResult.value = res.data
      await nextTick()
      drawSingle()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function drawSingle() {
  const el = document.getElementById('factor-chart')
  if (!el || !singleResult.value) return
  const chart = echarts.init(el, null, { renderer: 'canvas' })
  const data = singleResult.value.data
  const cols = Object.keys(data[0] || {}).filter(k => k !== 'date')
  const series = cols.map(col => ({
    name: col,
    type: 'line',
    data: data.map(r => [r.date, r[col]]),
    showSymbol: false,
    smooth: true,
  }))
  chart.setOption({
    backgroundColor: 'transparent',
    title: { text: `${selectedFactor.value.name_zh} (${selectedFactor.value.id})`, left: 'center',
      textStyle: { color: '#eaecef', fontSize: 14 } },
    tooltip: { trigger: 'axis', backgroundColor: '#181a20', borderColor: '#2b3139', textStyle: { color: '#eaecef' } },
    legend: { top: 30, textStyle: { color: '#b7bdc6' } },
    grid: { left: 60, right: 30, top: 80, bottom: 60 },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' }, splitLine: { lineStyle: { color: '#2b3139' } } },
    series,
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 10, backgroundColor: '#181a20' }]
  })
  window.addEventListener('resize', () => chart.resize())
}

async function computeCross() {
  if (corrFactors.value.length < 2) return
  corrLoading.value = true
  try {
    const res = await correlateFactors({
      symbol: symbol.value, factor_ids: corrFactors.value,
      period: corrPeriod.value, timeframe: timeframe.value,
      start: start.value, end: end.value,
    })
    corrResult.value = res.data
    await nextTick()
    drawCorr()
  } catch (e) {
    error.value = e.message
  } finally {
    corrLoading.value = false
  }
}

function drawCorr() {
  const el = document.getElementById('corr-chart')
  if (!el || !corrResult.value) return
  const chart = echarts.init(el, null, { renderer: 'canvas' })
  chart.setOption({
    backgroundColor: 'transparent',
    title: { text: '因子相关性热力图', left: 'center', textStyle: { color: '#eaecef', fontSize: 14 } },
    tooltip: {
      position: 'top',
      formatter: p => `${p.data[0]} vs ${p.data[1]}<br/>相关系数: ${p.data[2].toFixed(3)}`
    },
    grid: { top: 80, left: 100, right: 30, bottom: 80 },
    xAxis: { type: 'category', data: corrResult.value.columns, axisLabel: { color: '#b7bdc6', rotate: 45 } },
    yAxis: { type: 'category', data: corrResult.value.columns, axisLabel: { color: '#b7bdc6' } },
    visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal',
      left: 'center', bottom: 10, inRange: { color: ['#f6465d', '#181a20', '#02c076'] },
      textStyle: { color: '#b7bdc6' } },
    series: [{
      name: '相关系数', type: 'heatmap', data: (() => {
        const arr = []
        for (let i = 0; i < corrResult.value.columns.length; i++) {
          for (let j = 0; j < corrResult.value.columns.length; j++) {
            arr.push([corrResult.value.columns[i], corrResult.value.columns[j], corrResult.value.matrix[i][j]])
          }
        }
        return arr
      })(),
      label: { show: false },
    }]
  })
  window.addEventListener('resize', () => chart.resize())
}

async function computeRank() {
  if (!selectedFactor.value) return
  rankLoading.value = true
  try {
    const res = await rankFactors({
      symbols: allSymbols.value,
      factor_id: selectedFactor.value.id,
      params: params.value, timeframe: timeframe.value,
      start: start.value, end: end.value, top: 25,
    })
    rankResult.value = res.data
    await nextTick()
    drawRank()
  } catch (e) {
    error.value = e.message
  } finally {
    rankLoading.value = false
  }
}

function drawRank() {
  const el = document.getElementById('rank-chart')
  if (!el || !rankResult.value) return
  const chart = echarts.init(el, null, { renderer: 'canvas' })
  const data = rankResult.value.ranking
  chart.setOption({
    backgroundColor: 'transparent',
    title: { text: `${selectedFactor.value.name_zh} 当前值排名`, left: 'center', textStyle: { color: '#eaecef', fontSize: 14 } },
    tooltip: { trigger: 'axis', backgroundColor: '#181a20', borderColor: '#2b3139', textStyle: { color: '#eaecef' } },
    grid: { left: 80, right: 30, top: 80, bottom: 60 },
    xAxis: { type: 'value', axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' } },
    yAxis: { type: 'category', data: data.map(d => d.symbol).reverse(),
      axisLine: { lineStyle: { color: '#474d57' } }, axisLabel: { color: '#b7bdc6' } },
    series: [{
      type: 'bar', data: data.map(d => d.current).reverse(),
      itemStyle: { color: '#f0b90b' },
      label: { show: true, position: 'right', color: '#b7bdc6' }
    }]
  })
  window.addEventListener('resize', () => chart.resize())
}

const tab = ref('compute')
const summary = computed(() => singleResult.value?.summary || {})

function fmt(v) { return v === null || v === undefined ? '-' : Number(v).toFixed(4) }
function pctRank(v) { return v === null || v === undefined ? '-' : (v * 100).toFixed(1) + '%' }

loadFactorList()
</script>

<template>
  <div class="factor-page">
    <div class="tabs">
      <button :class="{ active: tab === 'compute' }" @click="tab = 'compute'">单因子查询</button>
      <button :class="{ active: tab === 'cross' }" @click="tab = 'cross'">多因子相关性</button>
      <button :class="{ active: tab === 'rank' }" @click="tab = 'rank'">跨币种排名</button>
    </div>

    <!-- 单因子 -->
    <div v-if="tab === 'compute'" class="card">
      <div class="form-row">
        <div class="form-group">
          <label>选择因子</label>
          <select v-model="selectedFactor">
            <optgroup v-for="cat in factorList.categories" :key="cat" :label="cat">
              <option v-for="f in factorList.factors.filter(f => f.category === cat)" :key="f.id" :value="f">
                {{ f.id }} - {{ f.name_zh }}
              </option>
            </optgroup>
          </select>
        </div>
        <div class="form-group">
          <label>币种</label>
          <input type="text" v-model="symbol" />
        </div>
        <div class="form-group">
          <label>K线</label>
          <input type="text" v-model="timeframe" />
        </div>
        <div class="form-group">
          <label>开始</label>
          <input type="text" v-model="start" />
        </div>
        <div class="form-group">
          <label>结束</label>
          <input type="text" v-model="end" />
        </div>
        <div v-for="(schema, key) in (selectedFactor?.params_schema || {})" :key="key" class="form-group">
          <label>{{ schema.label || key }}</label>
          <input type="number" v-model.number="params[key]"
            :min="schema.min" :max="schema.max" :step="schema.step || 1" />
        </div>
        <button class="btn-primary" @click="compute" :disabled="loading">
          {{ loading ? '计算中...' : '计算' }}
        </button>
      </div>
      <div v-if="selectedFactor" class="info-row">
        <div><strong>公式:</strong> <code>{{ selectedFactor.formula }}</code></div>
        <div><strong>说明:</strong> {{ selectedFactor.description }}</div>
      </div>
      <StateView :loading="loading" :error="error" empty-text="点击「计算」查看因子" empty-icon="🔍" v-if="!singleResult && !loading && !error" />
      <div v-if="summary.current" class="summary-grid">
        <div class="stat"><span class="lbl">当前值</span><span class="val">{{ fmt(summary.current) }}</span></div>
        <div class="stat"><span class="lbl">最小</span><span class="val">{{ fmt(summary.min) }}</span></div>
        <div class="stat"><span class="lbl">最大</span><span class="val">{{ fmt(summary.max) }}</span></div>
        <div class="stat"><span class="lbl">均值</span><span class="val">{{ fmt(summary.mean) }}</span></div>
        <div class="stat"><span class="lbl">中位数</span><span class="val">{{ fmt(summary.percentile_50) }}</span></div>
      </div>
      <div v-if="singleResult" id="factor-chart" class="chart"></div>
    </div>

    <!-- 多因子 -->
    <div v-if="tab === 'cross'" class="card">
      <div class="form-row">
        <div class="form-group grow">
          <label>选择 2+ 个因子 (逗号或回车分隔)</label>
          <input type="text" v-model="corrFactorsStr"
            placeholder="rsi,macd_hist,obv" @keyup.enter="computeCross" />
        </div>
        <div class="form-group">
          <label>回看 K 线数</label>
          <input type="number" v-model.number="corrPeriod" />
        </div>
        <div class="form-group">
          <label>币种</label>
          <input type="text" v-model="symbol" />
        </div>
        <button class="btn-primary" @click="computeCross" :disabled="corrLoading">
          {{ corrLoading ? '计算中...' : '计算相关性' }}
        </button>
      </div>
      <div v-if="corrFactors.length" class="chip-row">
        <span v-for="f in corrFactors" :key="f" class="chip">
          {{ f }}
          <button @click="corrFactors = corrFactors.filter(x => x !== f)">×</button>
        </span>
      </div>
      <div v-if="corrResult" id="corr-chart" class="chart-large"></div>
    </div>

    <!-- 跨币种排名 -->
    <div v-if="tab === 'rank'" class="card">
      <div class="form-row">
        <div class="form-group">
          <label>因子</label>
          <select v-model="selectedFactor">
            <option v-for="f in factorList.factors" :key="f.id" :value="f">
              {{ f.id }} - {{ f.name_zh }}
            </option>
          </select>
        </div>
        <button class="btn-primary" @click="computeRank" :disabled="rankLoading">
          {{ rankLoading ? '计算中...' : '排名' }}
        </button>
      </div>
      <div v-if="rankResult" id="rank-chart" class="chart-large"></div>
    </div>
  </div>
</template>

<style scoped>
.factor-page { display: flex; flex-direction: column; gap: 16px; }
.tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 8px;
}
.tabs button {
  background: transparent;
  color: var(--text-secondary);
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
}
.tabs button:hover { background: var(--bg-elevated); }
.tabs button.active { background: var(--yellow); color: #000; font-weight: 600; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.form-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.form-group { display: flex; flex-direction: column; gap: 4px; min-width: 120px; }
.form-group.grow { flex: 1; min-width: 200px; }
.form-group label { font-size: 11px; color: var(--text-secondary); }
.form-group input, .form-group select {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.form-group input:focus, .form-group select:focus { border-color: var(--yellow); }
.info-row {
  background: var(--bg);
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}
.info-row code { background: var(--bg-elevated); padding: 2px 6px; border-radius: 4px; color: var(--yellow); }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.stat {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 10px 12px;
  border-radius: 6px;
}
.stat .lbl { font-size: 11px; color: var(--text-secondary); }
.stat .val { font-size: 16px; font-weight: 600; font-family: 'Consolas', monospace; margin-top: 4px; }
.chart { height: 400px; }
.chart-large { height: 600px; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.chip {
  background: rgba(240,185,11,0.15);
  color: var(--yellow);
  padding: 4px 10px;
  border-radius: 14px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.chip button { background: transparent; color: var(--yellow); padding: 0 2px; font-size: 14px; }
</style>