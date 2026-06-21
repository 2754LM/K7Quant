<script setup>
import { ref, computed, watch, nextTick, inject, onUnmounted } from 'vue'
import { computeFactor, computeFactors, correlateFactors, rankFactors, listFactors,
  listRules, createRule, deleteRule, validateStrategyCode, createStrategy, getStrategies } from '../api'
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
const timeframe = ref('1d')
const start = ref('')
const end = ref('')

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

// 全部因子视图
const allFactorsResult = ref(null)
const allFactorsLoading = ref(false)
const allFactorsError = ref('')
const allFactorsFilter = ref('')  // 名称过滤
const allFactorsSortKey = ref('current')  // 排序列
const allFactorsSortDir = ref('desc')  // asc | desc
const allFactorsSelected = ref(new Set())  // 选中的因子 (workflow: 加入公式)

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
  for (const s of (cfg.value?.symbols || [])) {
    arr.push(s.symbol)
  }
  return arr.slice(0, 30)
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

// 全部因子: 单币种并行计算
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

const filteredAllFactors = computed(() => {
  if (!allFactorsResult.value) return []
  if (!allFactorsFilter.value) return allFactorsResult.value
  const t = allFactorsFilter.value.toLowerCase()
  return allFactorsResult.value.filter(r =>
    r.factor.name_zh.toLowerCase().includes(t) ||
    r.factor.id.toLowerCase().includes(t) ||
    r.factor.category.toLowerCase().includes(t)
  )
})

// 排序后
const sortedAllFactors = computed(() => {
  const arr = [...filteredAllFactors.value]
  const key = allFactorsSortKey.value
  const dir = allFactorsSortDir.value === 'asc' ? 1 : -1
  arr.sort((a, b) => {
    let va, vb
    if (key === 'name') {
      va = a.factor.name_zh
      vb = b.factor.name_zh
      return va.localeCompare(vb, 'zh-CN') * (dir > 0 ? 1 : -1)
    }
    va = a.data?.summary?.[key]
    vb = b.data?.summary?.[key]
    if (va == null) return 1
    if (vb == null) return -1
    return (va - vb) * dir
  })
  return arr
})

function sortBy(key) {
  if (allFactorsSortKey.value === key) {
    allFactorsSortDir.value = allFactorsSortDir.value === 'desc' ? 'asc' : 'desc'
  } else {
    allFactorsSortKey.value = key
    allFactorsSortDir.value = key === 'name' ? 'asc' : 'desc'
  }
}

// 选中行 (workflow: 加入公式)
function toggleFactorSelect(factorId) {
  if (allFactorsSelected.value.has(factorId)) {
    allFactorsSelected.value.delete(factorId)
  } else {
    allFactorsSelected.value.add(factorId)
  }
  allFactorsSelected.value = new Set(allFactorsSelected.value)
  buildFormulaFromSelection()
}

// 公式生成器: 根据选中的因子自动生成 signal 表达式
const generatedFormula = ref('')
function buildFormulaFromSelection() {
  const selected = allFactorsResult.value?.filter(r => allFactorsSelected.value.has(r.factor.id)) || []
  if (!selected.length) {
    generatedFormula.value = ''
    return
  }
  // 根据因子值是否 > 0 触发买入 (>0: 多头信号, <0: 空头)
  const parts = selected.map(r => {
    const fid = r.factor.id
    // 返回 0/1 signal: 取当前值 > 0 视为 1
    return `(${fid} > 0)`
  })
  // 默认: 全部因子都大于 0 才买入 (AND)
  generatedFormula.value = `signal = ${parts.join(' AND ')}\n止损 = 0.05\n止盈 = 0.15\n仓位 = 1.0`
}

function selectAll() {
  for (const r of filteredAllFactors.value) {
    allFactorsSelected.value.add(r.factor.id)
  }
  allFactorsSelected.value = new Set(allFactorsSelected.value)
  buildFormulaFromSelection()
}
function clearSelection() {
  allFactorsSelected.value = new Set()
  generatedFormula.value = ''
}

// 复制公式
async function copyFormula() {
  if (!generatedFormula.value) return
  try {
    await navigator.clipboard.writeText(generatedFormula.value)
    copyTip.value = '已复制 ✓'
    setTimeout(() => copyTip.value = '', 1500)
  } catch (e) {
    copyTip.value = '复制失败'
  }
}
const copyTip = ref('')

// 落库: 把生成的策略保存
const saveDialogOpen = ref(false)
const saveName = ref('')
const saveDesc = ref('')
const saveLoading = ref(false)
const saveError = ref('')
const saveSuccess = ref('')
const strategies = ref([])
async function loadStrategies() {
  try { strategies.value = (await getStrategies()).data.strategies } catch (e) {}
}
function openSaveDialog() {
  if (!generatedFormula.value) return
  // 默认名: 组合选中的因子名
  const ids = Array.from(allFactorsSelected.value)
  saveName.value = `组合: ${ids.join('+')}`
  saveDesc.value = `${symbol.value} ${timeframe.value} 因子组合策略`
  saveError.value = ''
  saveSuccess.value = ''
  saveDialogOpen.value = true
}
async function confirmSave() {
  if (!saveName.value.trim()) {
    saveError.value = '请输入策略名'
    return
  }
  if (!generatedFormula.value.trim()) {
    saveError.value = '公式为空'
    return
  }
  saveLoading.value = true
  try {
    // 先校验
    const valRes = await validateStrategyCode(generatedFormula.value)
    if (!valRes.data.ok) {
      saveError.value = `代码无效: ${valRes.data.error}`
      return
    }
    await createStrategy({
      name: saveName.value.trim(),
      description: saveDesc.value.trim() || '由因子组合生成',
      category: 'custom',
      code: generatedFormula.value,
      params_schema: {},
    })
    saveSuccess.value = '✓ 已保存'
    setTimeout(() => {
      saveDialogOpen.value = false
      saveSuccess.value = ''
    }, 1500)
    await loadStrategies()
  } catch (e) {
    saveError.value = e.message
  } finally {
    saveLoading.value = false
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

const tab = ref('all')  // 默认 all
const summary = computed(() => singleResult.value?.summary || {})

function fmt(v) { return v === null || v === undefined ? '-' : Number(v).toFixed(4) }
function pctRank(v) { return v === null || v === undefined ? '-' : (v * 100).toFixed(1) + '%' }
function sortIcon(key) {
  if (allFactorsSortKey.value !== key) return '↕'
  return allFactorsSortDir.value === 'asc' ? '↑' : '↓'
}

loadFactorList()
loadRules()
loadStrategies()
</script>

<template>
  <div class="factor-page">
    <div class="tabs">
      <button :class="{ active: tab === 'all' }" @click="tab = 'all'">📊 全部因子 (表格式)</button>
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
          <DateRangePicker v-model:start="start" v-model:end="end" :timeframe="timeframe" default-range="1m" />
        </div>
        <div v-for="(schema, key) in (selectedFactor?.params_schema || {})" :key="key" class="form-group">
          <label>
            {{ schema.label || key }}
            <span v-if="schema.unit" class="unit-hint">({{ schema.unit }})</span>
          </label>
          <input type="number" v-model.number="params[key]"
            :min="schema.min" :max="schema.max" :step="schema.step || 1"
            :title="schema.hint || ''" />
          <span v-if="schema.hint" class="param-hint">{{ schema.hint }}</span>
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

    <!-- 全部因子: 表格式 + workflow -->
    <div v-if="tab === 'all'" class="card">
      <div class="all-factors-header">
        <h3>📊 因子查询工作流</h3>
        <p class="workflow-hint">
          ① 顶部选择币种 + K线 + 区间 ② 点「计算全部」出表格 ③ 勾选因子自动生成公式 ④ 复制/保存为策略
        </p>
      </div>

      <!-- 顶部: 查询条件 -->
      <div class="form-row all-factors-form">
        <div class="form-group">
          <label>币种</label>
          <select v-model="symbol">
            <option v-for="s in allSymbols" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>K线</label>
          <TimeframePicker v-model="timeframe" />
        </div>
        <div class="form-group" style="grid-column: span 2; min-width: 360px">
          <label>日期区间</label>
          <DateRangePicker v-model:start="start" v-model:end="end" :timeframe="timeframe" default-range="1m" />
        </div>
        <button class="btn-primary" @click="computeAllFactors" :disabled="allFactorsLoading">
          {{ allFactorsLoading ? '计算中...' : '▶ 计算全部' }}
        </button>
      </div>

      <!-- 中部: 表格 + 操作 -->
      <div v-if="allFactorsResult?.length" class="all-result-section">
        <div class="all-result-toolbar">
          <div class="filter-bar">
            <input v-model="allFactorsFilter" type="text" placeholder="🔍 按名称/ID/分类过滤" class="filter-input" />
            <span class="result-count">共 {{ filteredAllFactors.length }} / {{ allFactorsResult.length }} 个因子</span>
            <span class="selected-count">已选 {{ allFactorsSelected.size }} 个</span>
            <button class="mini-btn" @click="selectAll" :disabled="!filteredAllFactors.length">勾选当前</button>
            <button class="mini-btn" @click="clearSelection" :disabled="!allFactorsSelected.size">清空</button>
          </div>
        </div>

        <!-- 表格: 因子 + 统计 + 选择 -->
        <div class="factor-table-wrap">
          <table class="factor-table">
            <thead>
              <tr>
                <th class="th-check">选</th>
                <th class="th-cat">分类</th>
                <th class="sortable th-name" @click="sortBy('name')">因子 <span class="arr">{{ sortIcon('name') }}</span></th>
                <th class="th-id">ID</th>
                <th class="th-desc">说明</th>
                <th class="sortable th-num" @click="sortBy('current')">当前 <span class="arr">{{ sortIcon('current') }}</span></th>
                <th class="sortable th-num" @click="sortBy('min')">最小 <span class="arr">{{ sortIcon('min') }}</span></th>
                <th class="sortable th-num" @click="sortBy('max')">最大 <span class="arr">{{ sortIcon('max') }}</span></th>
                <th class="sortable th-num" @click="sortBy('mean')">均值 <span class="arr">{{ sortIcon('mean') }}</span></th>
                <th class="sortable th-num" @click="sortBy('std')">标准差 <span class="arr">{{ sortIcon('std') }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in sortedAllFactors" :key="r.factor.id"
                :class="{ selected: allFactorsSelected.has(r.factor.id), error: r.error }"
                @click="toggleFactorSelect(r.factor.id)">
                <td class="td-check">
                  <input type="checkbox" :checked="allFactorsSelected.has(r.factor.id)"
                    @click.stop="toggleFactorSelect(r.factor.id)" />
                </td>
                <td class="td-cat">
                  <span class="cat-tag" :data-cat="r.factor.category">{{ r.factor.category }}</span>
                </td>
                <td class="td-name">
                  <span class="name-zh">{{ r.factor.name_zh }}</span>
                  <span class="name-en">{{ r.factor.name_en }}</span>
                </td>
                <td class="td-id"><code>{{ r.factor.id }}</code></td>
                <td class="td-desc" :title="r.factor.description">{{ r.factor.description }}</td>
                <td v-if="!r.error" class="td-num" :class="{ current: true }">
                  <span class="num-val" :class="{ neg: (r.data?.summary?.current ?? 0) < 0 }">{{ fmt(r.data?.summary?.current) }}</span>
                </td>
                <td v-else class="td-err" colspan="5">✗ {{ r.error }}</td>
                <td v-if="!r.error" class="td-num">{{ fmt(r.data?.summary?.min) }}</td>
                <td v-if="!r.error" class="td-num">{{ fmt(r.data?.summary?.max) }}</td>
                <td v-if="!r.error" class="td-num">{{ fmt(r.data?.summary?.mean) }}</td>
                <td v-if="!r.error" class="td-num">{{ fmt(r.data?.summary?.std) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 底部: 公式生成器 -->
        <div class="formula-builder" v-if="allFactorsSelected.size > 0">
          <div class="formula-head">
            <h4>📝 自动生成的公式 (signal: 所有选中因子都 > 0 时买入)</h4>
            <div class="formula-tools">
              <span v-if="copyTip" class="copy-tip">{{ copyTip }}</span>
              <button class="mini-btn" @click="copyFormula" :disabled="!generatedFormula">📋 复制</button>
              <button class="btn-primary" @click="openSaveDialog" :disabled="!generatedFormula">💾 保存为策略</button>
            </div>
          </div>
          <pre class="formula-code">{{ generatedFormula }}</pre>
          <div class="formula-hint">
            提示: 复制后到「自写策略」页面粘贴即可运行; 或直接点「保存为策略」入库
          </div>
        </div>
      </div>

      <StateView :loading="allFactorsLoading" :error="allFactorsError" empty-text="选币种，点计算查看所有因子" empty-icon="📊" v-if="!allFactorsResult && !allFactorsLoading && !allFactorsError" />

      <!-- 保存对话框 -->
      <div v-if="saveDialogOpen" class="modal-mask" @click.self="saveDialogOpen = false">
        <div class="modal">
          <div class="modal-head">
            <h3>💾 保存因子组合策略</h3>
            <button class="modal-close" @click="saveDialogOpen = false">×</button>
          </div>
          <div class="modal-body">
            <div v-if="saveSuccess" class="success-msg">{{ saveSuccess }}</div>
            <div class="form-row">
              <div class="form-group grow">
                <label>策略名 *</label>
                <input type="text" v-model="saveName" placeholder="输入策略名" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group grow">
                <label>说明</label>
                <input type="text" v-model="saveDesc" placeholder="一句话描述" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group grow">
                <label>代码预览</label>
                <pre class="code-preview">{{ generatedFormula }}</pre>
              </div>
            </div>
            <div v-if="saveError" class="error-msg">{{ saveError }}</div>
          </div>
          <div class="modal-foot">
            <button class="btn-secondary" @click="saveDialogOpen = false">取消</button>
            <button class="btn-primary" :disabled="saveLoading || !saveName.trim()" @click="confirmSave">
              {{ saveLoading ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
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
.form-group label { font-size: 11px; color: var(--text-secondary); display: flex; align-items: center; gap: 4px; }
.form-group input, .form-group select {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.form-group input:focus, .form-group select:focus { border-color: var(--yellow); }
.unit-hint { color: var(--text-muted); font-weight: 400; font-size: 10px; }
.param-hint { font-size: 10px; color: var(--text-muted); line-height: 1.3; margin-top: 2px; }
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

/* 全部因子 (workflow + table) */
.all-factors-header {
  background: var(--bg);
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 12px;
  border-left: 3px solid var(--yellow);
}
.all-factors-header h3 { font-size: 15px; margin-bottom: 4px; color: var(--yellow); }
.workflow-hint { font-size: 12px; color: var(--text-secondary); line-height: 1.5; }
.all-factors-form {
  background: var(--bg);
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
}
.all-result-toolbar { margin-top: 12px; margin-bottom: 12px; }
.filter-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.filter-input {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  flex: 1;
  min-width: 180px;
  outline: none;
}
.filter-input:focus { border-color: var(--yellow); }
.result-count, .selected-count { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.selected-count { color: var(--yellow); font-weight: 600; }
.mini-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
}
.mini-btn:hover:not(:disabled) { border-color: var(--yellow); color: var(--yellow); }
.mini-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* 因子表格 */
.factor-table-wrap {
  max-height: 600px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 16px;
}
.factor-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.factor-table thead {
  position: sticky;
  top: 0;
  background: var(--bg-elevated);
  z-index: 1;
}
.factor-table th {
  text-align: left;
  padding: 8px 10px;
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.factor-table th.sortable { cursor: pointer; }
.factor-table th.sortable:hover { color: var(--yellow); }
.factor-table th .arr { color: var(--yellow); margin-left: 2px; font-size: 10px; }
.factor-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  font-family: 'Consolas', monospace;
}
.factor-table tr {
  cursor: pointer;
  transition: background 0.1s;
}
.factor-table tbody tr:hover { background: var(--bg-elevated); }
.factor-table tr.selected { background: rgba(240,185,11,0.08); }
.factor-table tr.selected td { border-bottom-color: rgba(240,185,11,0.2); }
.factor-table tr.error { background: rgba(246,70,93,0.04); }
.factor-table tr.error:hover { background: rgba(246,70,93,0.08); }
.td-check { width: 32px; text-align: center; }
.factor-table input[type="checkbox"] { accent-color: var(--yellow); cursor: pointer; }
.td-cat { width: 80px; }
.cat-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
}
.cat-tag[data-cat="均线类"] { background: rgba(52,152,219,0.15); color: #5dade2; }
.cat-tag[data-cat="趋势类"] { background: rgba(46,204,113,0.15); color: #58d68d; }
.cat-tag[data-cat="震荡类"] { background: rgba(155,89,182,0.15); color: #bb8fce; }
.cat-tag[data-cat="动量类"] { background: rgba(241,196,15,0.15); color: #f4d03f; }
.cat-tag[data-cat="波动类"] { background: rgba(230,126,34,0.15); color: #f5b041; }
.cat-tag[data-cat="成交量类"] { background: rgba(26,188,156,0.15); color: #5dcead; }
.cat-tag[data-cat="形态类"] { background: rgba(243,104,224,0.15); color: #f195d8; }
.cat-tag[data-cat="风险类"] { background: rgba(231,76,60,0.15); color: #f1948a; }
.cat-tag[data-cat="统计类"] { background: rgba(149,165,166,0.15); color: #aab7b8; }
.td-name { min-width: 140px; }
.name-zh { display: block; font-weight: 600; color: var(--text); }
.name-en { display: block; font-size: 10px; color: var(--text-muted); margin-top: 1px; }
.td-id { width: 80px; }
.td-id code {
  background: var(--bg-elevated);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  color: var(--yellow);
}
.td-desc {
  max-width: 220px;
  font-family: inherit;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.td-num { text-align: right; min-width: 80px; }
.num-val { font-weight: 600; color: var(--yellow); }
.num-val.neg { color: var(--red); }
.td-err {
  font-size: 11px;
  color: var(--red);
  font-family: inherit;
  text-align: left;
}

/* 公式生成器 */
.formula-builder {
  background: var(--bg);
  border: 2px solid var(--yellow);
  border-radius: 8px;
  padding: 14px;
}
.formula-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.formula-head h4 { font-size: 13px; color: var(--yellow); }
.formula-tools { display: flex; gap: 6px; align-items: center; }
.copy-tip { font-size: 11px; color: var(--green); }
.formula-code {
  background: #0d0e10;
  border: 1px solid var(--border);
  padding: 12px 14px;
  border-radius: 6px;
  font-family: 'Consolas', monospace;
  font-size: 13px;
  color: #eaecef;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin-bottom: 6px;
}
.formula-hint { font-size: 11px; color: var(--text-muted); }

/* 模态框 */
.modal-mask {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.modal {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  width: 560px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: auto;
  box-shadow: 0 12px 32px rgba(0,0,0,0.5);
}
.modal-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid var(--border);
}
.modal-head h3 { font-size: 16px; }
.modal-close {
  background: transparent; border: 0; color: var(--text-muted);
  font-size: 24px; cursor: pointer; line-height: 1;
}
.modal-close:hover { color: var(--red); }
.modal-body { padding: 20px; }
.modal-body .form-row { margin-bottom: 12px; }
.modal-body .form-group label { font-size: 12px; color: var(--text-secondary); }
.modal-body .form-group input {
  background: var(--bg); border: 1px solid var(--border);
  color: var(--text); padding: 8px 12px; border-radius: 6px; font-size: 13px;
}
.modal-body .form-group input:focus { border-color: var(--yellow); }
.code-preview {
  background: #0d0e10; border: 1px solid var(--border); border-radius: 6px;
  padding: 10px 12px; font-family: 'Consolas', monospace; font-size: 12px;
  color: #eaecef; white-space: pre-wrap; max-height: 200px; overflow: auto;
}
.error-msg { color: var(--red); font-size: 12px; margin-top: 8px; }
.success-msg { color: var(--green); font-size: 13px; margin-bottom: 8px; }
.modal-foot {
  display: flex; gap: 8px; justify-content: flex-end;
  padding: 14px 20px; border-top: 1px solid var(--border);
}
.btn-primary {
  background: var(--yellow); color: #000; padding: 8px 16px;
  border-radius: 6px; font-weight: 600; font-size: 13px;
  border: 0; cursor: pointer;
}
.btn-primary:hover:not(:disabled) { background: #fcd535; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary {
  background: transparent; border: 1px solid var(--border);
  color: var(--text-secondary); padding: 8px 16px;
  border-radius: 6px; font-size: 13px; cursor: pointer;
}
.btn-secondary:hover { border-color: var(--text-secondary); }

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
