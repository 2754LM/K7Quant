<script setup>
import { ref, computed, watch, nextTick, inject } from 'vue'
import { computeFactor, computeFactors, correlateFactors, rankFactors, listFactors,
  listRules, createRule, deleteRule } from '../api'
import * as echarts from 'echarts'

const cfg = inject('cfg')

import StateView from '../components/StateView.vue'
import HelpTip from '../components/HelpTip.vue'
import DateRangePicker from '../components/DateRangePicker.vue'
import TimeframePicker from '../components/TimeframePicker.vue'

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

// 全部因子视图: 选中币种后并行算所有因子
const allFactorsResult = ref(null)
const allFactorsLoading = ref(false)
const allFactorsError = ref('')

watch(corrFactorsStr, (v) => {
  corrFactors.value = v.split(/[,\s]+/).filter(Boolean)
})

function toggleCorrFactor(fid) {
  const i = corrFactors.value.indexOf(fid)
  if (i >= 0) corrFactors.value.splice(i, 1)
  else corrFactors.value.push(fid)
  corrFactorsStr.value = corrFactors.value.join(',')
}

// ---- 自定义规则 (落库 custom_rules) ----
const savedRules = ref([])
async function loadRules() {
  try { savedRules.value = (await listRules()).data.rules } catch (e) { /* ignore */ }
}
async function saveCurrentAsRule() {
  if (corrFactors.value.length < 2) return
  const name = prompt('规则名称', `相关性: ${corrFactors.value.join('+')}`)
  if (!name) return
  await createRule({
    name,
    description: `${symbol.value} ${timeframe.value} 因子相关性查询`,
    rule_json: {
      type: 'correlation', symbol: symbol.value, timeframe: timeframe.value,
      factor_ids: corrFactors.value, period: corrPeriod.value,
    },
  })
  await loadRules()
}
function applyRule(r) {
  const j = r.rule_json || {}
  if (j.factor_ids) corrFactorsStr.value = j.factor_ids.join(',')
  if (j.symbol) symbol.value = j.symbol
  if (j.timeframe) timeframe.value = j.timeframe
  if (j.period) corrPeriod.value = j.period
  tab.value = 'cross'
}
async function delRule(id) {
  await deleteRule(id)
  await loadRules()
}

const allSymbols = computed(() => {
  const arr = []
  for (const s of (factorList.value.factors || [])) {
    if (!arr.includes(s.symbol)) arr.push(s.symbol)
  }
  return arr.slice(0, 25)
})

const timeframes = computed(() => cfg.value?.timeframes || ['1d'])

// 用于多因子相关性的选择列表: 全部因子按 category 分组
const allFactorChips = computed(() => {
  const out = []
  for (const cat of factorList.value.categories || []) {
    const fs = factorList.value.factors.filter(f => f.category === cat)
    if (fs.length) out.push({ category: cat, factors: fs })
  }
  return out
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

// 全部因子 (单币种并行计算所有因子)
async function computeAllFactors() {
  if (!factorList.value.factors.length) return
  allFactorsLoading.value = true
  allFactorsError.value = ''
  allFactorsResult.value = null
  try {
    const factors = factorList.value.factors
    const results = await Promise.allSettled(
      factors.map(f => computeFactor({
        symbol: symbol.value, factor_id: f.id,
        params: f.params_schema ? Object.fromEntries(
          Object.entries(f.params_schema).map(([k, s]) => [k, s.default])
        ) : {},
        timeframe: timeframe.value, start: start.value, end: end.value,
      }).then(r => ({ factor: f, data: r.data }))
        .catch(e => ({ factor: f, error: e.message })))
    )
    allFactorsResult.value = results
      .filter(r => r.status === 'fulfilled')
      .map(r => r.value)
  } catch (e) {
    allFactorsError.value = e.message
  } finally {
    allFactorsLoading.value = false
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
loadRules()
</script>

<template>
  <div class="factor-page">
    <div class="tabs">
      <button :class="{ active: tab === 'all' }" @click="tab = 'all'">📊 全部因子</button>
      <button :class="{ active: tab === 'compute' }" @click="tab = 'compute'">单因子</button>
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
          <TimeframePicker v-model="timeframe" />
        </div>
        <div class="form-group" style="grid-column: span 2; min-width: 360px">
          <label>日期区间</label>
          <DateRangePicker v-model:start="start" v-model:end="end" default-range="3m" />
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
          <label>币种</label>
          <input type="text" v-model="symbol" />
        </div>
        <div class="form-group">
          <label>回看 K 线数</label>
          <input type="number" v-model.number="corrPeriod" />
        </div>
        <button class="btn-primary" @click="computeCross" :disabled="corrLoading || corrFactors.length < 2">
          {{ corrLoading ? '计算中...' : '计算相关性' }}
        </button>
      </div>
      <div class="factor-picker">
        <div v-for="g in allFactorChips" :key="g.category" class="fp-group">
          <div class="fp-cat">{{ g.category }}</div>
          <div class="fp-chips">
            <button v-for="f in g.factors" :key="f.id"
              :class="['fp-chip', { active: corrFactors.includes(f.id) }]"
              @click="toggleCorrFactor(f.id)"
              :title="f.description">
              {{ f.name_zh }}
            </button>
          </div>
        </div>
      </div>
      <div v-if="corrFactors.length" class="chip-row">
        <span class="hint">已选: </span>
        <span v-for="f in corrFactors" :key="f" class="chip">
          {{ factorList.factors.find(x => x.id === f)?.name_zh || f }}
          <button @click="toggleCorrFactor(f)">×</button>
        </span>
      </div>
      <div class="rules-bar">
        <button class="btn-secondary" @click="saveCurrentAsRule" :disabled="corrFactors.length < 2">💾 保存为规则</button>
        <span v-for="r in savedRules" :key="r.id" class="rule-chip" :title="r.description">
          <span class="rule-name" @click="applyRule(r)">{{ r.name }}</span>
          <button @click="delRule(r.id)">×</button>
        </span>
        <span v-if="!savedRules.length" class="rules-empty">暂无保存的规则</span>
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

    <!-- 全部因子 (单币种) -->
    <div v-if="tab === 'all'" class="card">
      <div class="form-row">
        <div class="form-group">
          <label>币种</label>
          <input type="text" v-model="symbol" />
        </div>
        <div class="form-group">
          <label>K线</label>
          <TimeframePicker v-model="timeframe" />
        </div>
        <div class="form-group" style="grid-column: span 2; min-width: 360px">
          <label>日期区间</label>
          <DateRangePicker v-model:start="start" v-model:end="end" default-range="3m" />
        </div>
        <button class="btn-primary" @click="computeAllFactors" :disabled="allFactorsLoading">
          {{ allFactorsLoading ? '计算中...' : '▶ 计算全部' }}
        </button>
      </div>
      <div v-if="allFactorsResult?.length" class="all-factors-grid">
        <div v-for="r in allFactorsResult" :key="r.factor.id" class="factor-card">
          <div class="fc-head">
            <span class="fc-name">{{ r.factor.name_zh }}</span>
            <span class="fc-id">{{ r.factor.id }}</span>
            <span v-if="r.error" class="fc-err" :title="r.error">✗</span>
          </div>
          <div v-if="r.data && !r.error" class="fc-stats">
            <div class="fc-stat"><span class="lbl">当前</span><span class="val">{{ fmt(r.data.summary?.current) }}</span></div>
            <div class="fc-stat"><span class="lbl">最小</span><span class="val">{{ fmt(r.data.summary?.min) }}</span></div>
            <div class="fc-stat"><span class="lbl">最大</span><span class="val">{{ fmt(r.data.summary?.max) }}</span></div>
            <div class="fc-stat"><span class="lbl">均值</span><span class="val">{{ fmt(r.data.summary?.mean) }}</span></div>
          </div>
          <div v-if="r.error" class="fc-error">{{ r.error }}</div>
          <div v-if="r.data && !r.error" class="fc-desc">{{ r.factor.description }}</div>
        </div>
      </div>
      <StateView :loading="allFactorsLoading" :error="allFactorsError" empty-text="选币种，点计算查看所有因子" empty-icon="📊" v-if="!allFactorsResult && !allFactorsLoading && !allFactorsError" />
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
.rules-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.rules-empty { font-size: 12px; color: var(--text-muted); }
.rule-chip {
  display: flex; align-items: center; gap: 6px;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 14px; padding: 3px 6px 3px 10px; font-size: 12px;
}
.rule-chip .rule-name { cursor: pointer; color: var(--text); }
.rule-chip .rule-name:hover { color: var(--yellow); }
.rule-chip button { background: transparent; color: var(--red); padding: 0 2px; font-size: 13px; }

/* 全部因子网格 */
.all-factors-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.factor-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  transition: border-color 0.2s;
}
.factor-card:hover { border-color: var(--yellow); }
.fc-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.fc-name { font-size: 13px; font-weight: 600; color: var(--text); flex: 1; }
.fc-id { font-size: 10px; color: var(--text-muted); font-family: 'Consolas', monospace; }
.fc-err { color: var(--red); font-size: 14px; }
.fc-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 4px;
  margin-bottom: 6px;
}
.fc-stat { display: flex; flex-direction: column; gap: 1px; }
.fc-stat .lbl { font-size: 10px; color: var(--text-muted); }
.fc-stat .val { font-size: 13px; font-family: 'Consolas', monospace; color: var(--yellow); font-weight: 600; }
.fc-desc { font-size: 11px; color: var(--text-secondary); line-height: 1.4; }
.fc-error { font-size: 11px; color: var(--red); }

/* 因子选择器 (多因子相关性) */
.factor-picker {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  max-height: 280px;
  overflow-y: auto;
}
.fp-group { margin-bottom: 10px; }
.fp-group:last-child { margin-bottom: 0; }
.fp-cat {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
  font-weight: 600;
}
.fp-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.fp-chip {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 14px;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
}
.fp-chip:hover { border-color: var(--yellow); color: var(--text); }
.fp-chip.active {
  background: var(--yellow);
  color: #000;
  border-color: var(--yellow);
  font-weight: 600;
}
</style>