<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted, inject } from 'vue'
import { scanPool, runBacktest, backtestCode, validateStrategyCode, createStrategy } from '../api'
import * as echarts from 'echarts'

import MetricCard from '../components/MetricCard.vue'
import StrategyPicker from '../components/StrategyPicker.vue'
import TimeframePicker from '../components/TimeframePicker.vue'
import DateRangePicker from '../components/DateRangePicker.vue'
import StateView from '../components/StateView.vue'
import HelpTip from '../components/HelpTip.vue'

const cfg = inject('cfg')
const reloadCfg = inject('reload')

const codePanelOpen = ref(false)
const tfMode = ref('single') // 'single' | 'multi'
const multiTfs = ref(['4h', '1d', '1w'])
const multiResults = ref(null)

// ---------- 预设策略回测 ----------
const params = ref({
  strategy_id: null,
  timeframe: '4h',
  symbols: null,         // null = 使用全部活跃币种
  weights: null,         // null = 等权; {symbol: weight} = 自定义权重
  ma_short: 7, ma_long: 25,
  top_n: 3, hold: 12, lookback: 24,
  rsi_period: 14, rsi_oversold: 30, rsi_overbought: 70,
  macd_fast: 12, macd_slow: 26, macd_signal: 9,
  start_date: '20240101', end_date: '20250601',
})

// ---------- 币池选择 ----------
const poolMode = ref('all')  // 'all' | 'custom'
const poolSelection = ref(new Set())  // 用户选择的币种
const poolPickerOpen = ref(false)
const poolSearch = ref('')

const allActiveSymbols = computed(() => {
  const active = cfg.value?.active_symbols || []
  if (active.length) return active
  return (cfg.value?.symbols || []).filter(s => s.is_active !== false).map(s => s.symbol)
})
const allSymbolsList = computed(() => (cfg.value?.symbols || []).map(s => s.symbol))
const filteredPoolList = computed(() => {
  const t = poolSearch.value.trim().toLowerCase()
  const symInfo = {}
  for (const s of (cfg.value?.symbols || [])) symInfo[s.symbol] = s
  let list = allSymbolsList.value
  if (t) list = list.filter(s => s.toLowerCase().includes(t) || (symInfo[s]?.name_zh || '').toLowerCase().includes(t))
  return list.map(s => ({ symbol: s, name: symInfo[s]?.name_zh || '' }))
})
const effectivePoolCount = computed(() => {
  if (poolMode.value === 'all') return allActiveSymbols.value.length
  return poolSelection.value.size
})
const effectivePoolLabel = computed(() => {
  if (poolMode.value === 'all') return `全部活跃 (${allActiveSymbols.value.length})`
  return `自定义 (${poolSelection.value.size})`
})

// 同步 params.symbols, 给 scan_pool 用
watch([poolMode, poolSelection], () => {
  if (poolMode.value === 'all') {
    params.value.symbols = null
  } else {
    params.value.symbols = Array.from(poolSelection.value)
  }
}, { deep: true, immediate: true })

function togglePoolSymbol(sym) {
  if (poolSelection.value.has(sym)) poolSelection.value.delete(sym)
  else poolSelection.value.add(sym)
  poolSelection.value = new Set(poolSelection.value)
}
function selectAllFromList() {
  for (const s of filteredPoolList.value) poolSelection.value.add(s.symbol)
  poolSelection.value = new Set(poolSelection.value)
}
function clearPoolSelection() { poolSelection.value = new Set() }

// ---------- 持仓权重 ----------
const weightMode = ref('equal')  // 'equal' | 'custom'
const weights = ref({})          // {symbol: weight}
const weightOpen = ref(false)
function effectivePoolSymbols() {
  if (poolMode.value === 'all') return allActiveSymbols.value
  return Array.from(poolSelection.value)
}
const weightTotal = computed(() => {
  const syms = effectivePoolSymbols()
  if (weightMode.value === 'equal') return syms.length
  return syms.reduce((s, x) => s + (Number(weights.value[x]) || 0), 0)
})
const weightValid = computed(() => {
  const syms = effectivePoolSymbols()
  if (syms.length === 0) return false
  if (weightMode.value === 'equal') return true
  return weightTotal.value > 0
})
function normalizeWeights() {
  // 把权重归一化到 sum=1 (后端会再归一化一次, 这里只是预览用)
  const syms = effectivePoolSymbols()
  if (weightMode.value === 'equal' || weightTotal.value === 0) {
    const eq = syms.length ? 1 / syms.length : 0
    const obj = {}
    for (const s of syms) obj[s] = eq
    return obj
  }
  const obj = {}
  for (const s of syms) obj[s] = (Number(weights.value[s]) || 0) / weightTotal.value
  return obj
}
function distributeEqual() {
  // 把当前权重全部设为 1, 后端归一化后 = 等权
  const syms = effectivePoolSymbols()
  for (const s of syms) weights.value[s] = 1
}
function setWeight(sym, v) {
  const n = Number(v)
  if (isNaN(n) || n < 0) weights.value[sym] = 0
  else weights.value[sym] = n
}
function presetByCap() {
  // 按市值大致分: 主流币权重大, 长尾小 (示例: BTC 4, ETH 3, 其他 1)
  const syms = effectivePoolSymbols()
  for (const s of syms) {
    if (s === 'BTCUSDT') weights.value[s] = 4
    else if (s === 'ETHUSDT') weights.value[s] = 3
    else weights.value[s] = 1
  }
}

// 把 weights 同步给 params
watch([weightMode, weights, () => Array.from(poolSelection.value).join(','), poolMode], () => {
  if (weightMode.value === 'equal') {
    params.value.weights = null
  } else {
    const syms = effectivePoolSymbols()
    const obj = {}
    for (const s of syms) {
      const w = Number(weights.value[s])
      if (w > 0) obj[s] = w
    }
    params.value.weights = Object.keys(obj).length ? obj : null
  }
}, { deep: true, immediate: true })

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
  run()
}, { immediate: false })

watch([
  () => params.value.start_date,
  () => params.value.end_date,
  () => params.value.timeframe,
  () => params.value.symbols,
], () => {
  if (tfMode.value === 'single') run()
})

// ---------- 自定义代码面板 ----------
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
const codeValidation = ref(null)  // { ok, error, rules }
let codeChart = null
let codeValidationTimer = null

const allSymbols = computed(() => (cfg.value?.symbols || []).map(s => s.symbol))

// 实时校验 (debounce 400ms)
watch(() => codeForm.value.code, () => {
  if (codeValidationTimer) clearTimeout(codeValidationTimer)
  if (!codeForm.value.code.trim()) {
    codeValidation.value = null
    return
  }
  codeValidationTimer = setTimeout(async () => {
    try {
      const res = await validateStrategyCode(codeForm.value.code)
      codeValidation.value = res.data
    } catch (e) {
      codeValidation.value = { ok: false, error: e.message }
    }
  }, 400)
})

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
    if (res.data?.error) {
      codeError.value = res.data.error
    } else {
      codeResult.value = res.data
      await nextTick()
      drawCodeChart()
    }
  } catch (e) {
    codeError.value = e.message
  } finally {
    codeLoading.value = false
  }
}

function toggleCodePanel() {
  codePanelOpen.value = !codePanelOpen.value
  if (codePanelOpen.value) {
    // 第一次展开时做一次校验
    if (codeValidation.value === null && codeForm.value.code.trim()) {
      validateStrategyCode(codeForm.value.code)
        .then(r => codeValidation.value = r.data)
        .catch(e => codeValidation.value = { ok: false, error: e.message })
    }
  }
}

const saveDialogOpen = ref(false)
const saveForm = ref({ name: '', description: '', category: 'custom' })
const saving = ref(false)
const saveError = ref('')
const saveSuccess = ref('')

function openSaveDialog() {
  if (!codeValidation.value?.ok) {
    saveError.value = '代码语法不正确, 无法保存'
    return
  }
  // 默认名: 从已有策略名 + 自定义标记
  const baseName = activeStrategy.value?.name || '自定义策略'
  saveForm.value = {
    name: `${baseName}-自定义`,
    description: codeValidation.value?.rules?.signal ? `signal: ${codeValidation.value.rules.signal}` : '',
    category: 'custom',
  }
  saveError.value = ''
  saveSuccess.value = ''
  saveDialogOpen.value = true
}

async function confirmSave() {
  if (!saveForm.value.name.trim()) {
    saveError.value = '请输入策略名'
    return
  }
  saving.value = true
  saveError.value = ''
  try {
    const res = await createStrategy({
      name: saveForm.value.name.trim(),
      description: saveForm.value.description.trim(),
      category: saveForm.value.category,
      code: codeForm.value.code,
      params_schema: {},
    })
    if (res.data?.error) {
      saveError.value = res.data.error
    } else {
      saveSuccess.value = `✓ 已保存: ${saveForm.value.name}`
      // 刷新策略列表
      if (reloadCfg) await reloadCfg()
      setTimeout(() => {
        saveDialogOpen.value = false
        saveSuccess.value = ''
      }, 1500)
    }
  } catch (e) {
    saveError.value = e.message
  } finally {
    saving.value = false
  }
}

function getOrInitCodeChart(elId) {
  const el = document.getElementById(elId)
  if (!el) return null
  if (!codeChart || codeChart.getDom() !== el) {
    if (codeChart) { try { codeChart.dispose() } catch (e) {} }
    codeChart = echarts.init(el, null, { renderer: 'canvas' })
  }
  return codeChart
}

function drawCodeChart() {
  if (!codeResult.value?.equity?.length) return
  const c = getOrInitCodeChart('code-equity-chart')
  if (!c) return
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
  c.setOption({
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

const codeMetrics = computed(() => codeResult.value?.metrics || {})

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

// 排名过滤: 默认全选, 用户可取消
const visibleRanking = ref(new Set())  // 空 Set = 显示全部
const symbolFilterText = ref('')
function toggleRankingSymbol(sym) {
  if (visibleRanking.value.has(sym)) visibleRanking.value.delete(sym)
  else visibleRanking.value.add(sym)
}
function clearRankingFilter() {
  visibleRanking.value = new Set()
  symbolFilterText.value = ''
}
const filteredRanking = computed(() => {
  let arr = ranking.value
  if (visibleRanking.value.size > 0) {
    arr = arr.filter(r => visibleRanking.value.has(r.symbol))
  }
  if (symbolFilterText.value) {
    const t = symbolFilterText.value.toLowerCase()
    arr = arr.filter(r =>
      r.symbol.toLowerCase().includes(t) ||
      (symbolInfo.value[r.symbol]?.name_zh || '').includes(t)
    )
  }
  return arr
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

function getOrInitChart(elId) {
  const el = document.getElementById(elId)
  if (!el) return null
  if (!chart || chart.getDom() !== el) {
    if (chart) { try { chart.dispose() } catch (e) {} }
    chart = echarts.init(el, null, { renderer: 'canvas' })
  }
  return chart
}

function drawChart() {
  if (!result.value?.combined_equity?.length) return
  const c = getOrInitChart('equity-chart')
  if (!c) return
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
  c.setOption({
    backgroundColor: 'transparent',
    title: { text: `币池组合 (${result.value.count} 个币种 · ${result.value.timeframe}${result.value.weight_mode && result.value.weight_mode !== '等权' ? ' · ' + result.value.weight_mode : ''})`,
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
  const c = getOrInitChart('equity-chart')
  if (!c) return
  const series = multiResults.value.map((r, i) => {
    if (!r.ok || !r.data?.combined_equity?.length) return null
    const e0 = r.data.combined_equity[0].equity
    const data = r.data.combined_equity.map(rr => [rr.date, rr.equity / e0])
    return {
      name: r.tf, type: 'line', data, smooth: true, showSymbol: false,
      lineStyle: { width: 2, color: MULTI_COLORS[i % MULTI_COLORS.length] }
    }
  }).filter(Boolean)
  c.setOption({
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
    <div class="top-bar">
      <StrategyPicker :strategies="strategies" v-model="params.strategy_id" @change="run" />
      <button class="code-toggle" :class="{ active: codePanelOpen }"
        @click="toggleCodePanel" :title="codePanelOpen ? '关闭自定义代码' : '打开自定义代码'">
        🧪 {{ codePanelOpen ? '收起代码' : '自定义代码' }}
      </button>
      <div class="tf-mode-toggle">
        <button :class="{ active: tfMode === 'single' }" @click="tfMode = 'single'">单周期</button>
        <button :class="{ active: tfMode === 'multi' }" @click="tfMode = 'multi'">多周期对比</button>
      </div>
      <template v-if="tfMode === 'single'">
        <TimeframePicker v-model="params.timeframe" @change="run" />
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
        <!-- 币池选择 -->
        <div class="cfg pool-cfg">
          <label>币池 <span class="pool-count">({{ effectivePoolCount }})</span></label>
          <div class="pool-picker">
            <button class="pool-toggle" :class="{ active: poolMode === 'all' }"
              @click="poolMode = 'all'" title="扫描所有活跃币种">全部活跃</button>
            <button class="pool-toggle" :class="{ active: poolMode === 'custom' }"
              @click="poolMode = 'custom'; poolPickerOpen = true" title="选择指定币种">自定义</button>
            <button v-if="poolMode === 'custom'" class="pool-edit"
              @click="poolPickerOpen = !poolPickerOpen" :title="poolPickerOpen ? '收起选择器' : '打开选择器'">
              {{ poolPickerOpen ? '收起' : '编辑' }}
            </button>
            <transition name="slide">
              <div v-if="poolMode === 'custom' && poolPickerOpen" class="pool-panel">
                <div class="pool-tools">
                  <input v-model="poolSearch" type="text" class="pool-search" placeholder="🔍 搜索币种/名称..." />
                  <button class="pool-mini" @click="selectAllFromList">勾选当前</button>
                  <button class="pool-mini" @click="clearPoolSelection">清空</button>
                  <span class="pool-hint">已选 {{ poolSelection.size }} 个</span>
                </div>
                <div class="pool-grid">
                  <label v-for="s in filteredPoolList" :key="s.symbol"
                    :class="['pool-chip', { active: poolSelection.has(s.symbol) }]">
                    <input type="checkbox" :checked="poolSelection.has(s.symbol)"
                      @change="togglePoolSymbol(s.symbol)" />
                    <span class="pool-sym">{{ s.symbol }}</span>
                    <span class="pool-name">{{ s.name }}</span>
                  </label>
                  <div v-if="!filteredPoolList.length" class="pool-empty">未找到币种</div>
                </div>
              </div>
            </transition>
          </div>
        </div>
        <!-- 持仓权重 -->
        <div class="cfg weight-cfg" v-if="effectivePoolCount > 0">
          <label>持仓权重 <span class="weight-hint" v-if="weightMode === 'custom'">Σ={{ weightTotal.toFixed(2) }} → 归一化</span></label>
          <div class="weight-picker">
            <button class="pool-toggle" :class="{ active: weightMode === 'equal' }"
              @click="weightMode = 'equal'" title="每个币种仓位相等">等权</button>
            <button class="pool-toggle" :class="{ active: weightMode === 'custom' }"
              @click="weightMode = 'custom'; weightOpen = true" title="为每个币种设置不同权重">自定义</button>
            <button v-if="weightMode === 'custom'" class="pool-edit"
              @click="weightOpen = !weightOpen" :title="weightOpen ? '收起权重编辑' : '编辑权重'">
              {{ weightOpen ? '收起' : '编辑' }}
            </button>
            <transition name="slide">
              <div v-if="weightMode === 'custom' && weightOpen" class="weight-panel">
                <div class="weight-tools">
                  <button class="pool-mini" @click="distributeEqual" title="全部设为 1 (后端会归一化)">全部 = 1</button>
                  <button class="pool-mini" @click="presetByCap" title="BTC 4 / ETH 3 / 其他 1">按市值预设</button>
                  <span class="pool-hint">当前共 {{ effectivePoolCount }} 个币种, 总权重 {{ weightTotal.toFixed(2) }}</span>
                </div>
                <div class="weight-list">
                  <div v-for="sym in effectivePoolSymbols()" :key="sym" class="weight-row">
                    <span class="weight-sym">{{ sym }}</span>
                    <input type="number" min="0" step="0.1"
                      :value="weights[sym] ?? 1"
                      @input="setWeight(sym, $event.target.value)"
                      class="weight-input" />
                    <span class="weight-bar-wrap">
                      <span class="weight-bar"
                        :style="{ width: (normalizeWeights()[sym] * 100 || 0) + '%' }"></span>
                    </span>
                    <span class="weight-pct">{{ (normalizeWeights()[sym] * 100 || 0).toFixed(1) }}%</span>
                  </div>
                  <div v-if="!effectivePoolCount" class="pool-empty">请先选择币池</div>
                </div>
                <div v-if="!weightValid" class="weight-warn">⚠ 权重总和为 0, 请至少设置一个币种</div>
              </div>
            </transition>
          </div>
        </div>
        <div v-if="activeStrategy?.description" class="desc-box">
          <span>💡</span>
          <span>{{ activeStrategy.description }}</span>
        </div>
      </div>

      <!-- 自定义代码面板 (可折叠) -->
      <transition name="slide">
        <div v-if="codePanelOpen" class="code-card">
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
                <TimeframePicker v-model="codeForm.timeframe" />
              </div>
              <div class="form-group">
                <label>区间</label>
                <DateRangePicker v-model:start="codeForm.start_date" v-model:end="codeForm.end_date" default-range="3m" />
              </div>
              <button class="btn-primary" :disabled="codeLoading || !codeValidation?.ok" @click="runCode" :title="!codeValidation?.ok ? '请先修正代码语法' : ''">
                {{ codeLoading ? '运行中...' : '▶ 运行回测' }}
              </button>
              <button class="btn-secondary" :disabled="!codeValidation?.ok || saving" @click="openSaveDialog"
                :title="!codeValidation?.ok ? '请先修正代码语法' : '保存为新策略'">
                💾 保存为策略
              </button>
            </div>
          </div>
          <div class="editor-section">
            <div class="editor-head">
              <label class="editor-label">策略代码 (DSL)</label>
              <div class="code-status" :class="codeValidation?.ok ? 'ok' : codeValidation?.error ? 'err' : ''">
                <span v-if="codeValidation?.ok">✓ 语法正确{{ codeValidation.rules?.stop_loss ? ` · 止损 ${(codeValidation.rules.stop_loss*100).toFixed(0)}%` : '' }}{{ codeValidation.rules?.take_profit ? ` · 止盈 ${(codeValidation.rules.take_profit*100).toFixed(0)}%` : '' }}</span>
                <span v-else-if="codeValidation?.error">✗ {{ codeValidation.error }}</span>
                <span v-else class="muted">检测中...</span>
              </div>
            </div>
            <textarea v-model="codeForm.code" class="code-input" rows="6"
              placeholder="signal = CROSS_UP(MA(close, 7), MA(close, 25))"></textarea>
            <div class="code-hint">signal = 表达式 (必需) | 止损/止盈/仓位/频率 (可选) · 改完自动校验</div>
          </div>
          <StateView :loading="codeLoading" :error="codeError" empty-text="点击「运行回测」查看结果" empty-icon="▶" v-if="codePanelOpen && !codeResult && !codeLoading && !codeError" />
        </div>
      </transition>

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
          <h3>单币表现排名 <span class="count-chip">{{ filteredRanking.length }} / {{ result.count }}</span></h3>
          <div class="ranking-tools">
            <input v-model="symbolFilterText" type="text" class="symbol-search"
              placeholder="🔍 搜索币种..." />
            <button v-if="visibleRanking.size || symbolFilterText" class="btn-clear" @click="clearRankingFilter">
              ✗ 清空筛选
            </button>
            <span class="sort-tip">点击表头切换排序</span>
          </div>
        </div>
        <div class="ranking-chips">
          <span class="chip-label">显示币种:</span>
          <button v-for="r in ranking" :key="r.symbol"
            :class="['r-chip', { active: visibleRanking.size === 0 || visibleRanking.has(r.symbol) }]"
            @click="toggleRankingSymbol(r.symbol)">
            {{ r.symbol }}
            <span v-if="visibleRanking.size === 0 || visibleRanking.has(r.symbol)" class="r-dot"></span>
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>币种</th>
              <th>名称</th>
              <th class="sortable" @click="sortBy('total_return')">总收益 <span class="arr">{{ sortKey==='total_return' ? (sortDir==='desc'?'↓':'↑') : '↕' }}</span></th>
              <th class="sortable" @click="sortBy('sharpe')">夏普 <span class="arr">{{ sortKey==='sharpe' ? (sortDir==='desc'?'↓':'↑') : '↕' }}</span></th>
              <th class="sortable" @click="sortBy('calmar')">Calmar <span class="arr">{{ sortKey==='calmar' ? (sortDir==='desc'?'↓':'↑') : '↕' }}</span></th>
              <th class="sortable" @click="sortBy('max_drawdown')">回撤 <span class="arr">{{ sortKey==='max_drawdown' ? (sortDir==='desc'?'↓':'↑') : '↕' }}</span></th>
              <th class="sortable" @click="sortBy('win_rate')">胜率 <span class="arr">{{ sortKey==='win_rate' ? (sortDir==='desc'?'↓':'↑') : '↕' }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in filteredRanking" :key="r.symbol" :class="{ top: i < 3 }">
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

      <!-- 自定义代码回测结果 -->
      <template v-if="codePanelOpen && codeResult">
        <div class="card code-result-card">
          <h3>🧪 自定义代码回测结果 ({{ codeForm.symbol }} · {{ codeForm.timeframe }})</h3>
          <div class="metrics-grid" style="grid-template-columns: repeat(8, 1fr)">
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
          <div v-if="codeResult.trades?.length" class="trades-section" style="background: transparent; border: 0; padding: 0; margin-top: 12px">
            <h4>交易记录 ({{ codeResult.trades.length }})</h4>
            <table>
              <thead>
                <tr><th>时间</th><th>方向</th><th>价格</th><th>数量</th><th>金额</th></tr>
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
        </div>
      </template>

      <!-- 保存策略对话框 -->
      <div v-if="saveDialogOpen" class="modal-mask" @click.self="saveDialogOpen = false">
        <div class="modal">
          <div class="modal-head">
            <h3>💾 保存为新策略</h3>
            <button class="modal-close" @click="saveDialogOpen = false">×</button>
          </div>
          <div class="modal-body">
            <div v-if="saveSuccess" class="success-msg">{{ saveSuccess }}</div>
            <div class="form-row">
              <div class="form-group grow">
                <label>策略名 *</label>
                <input type="text" v-model="saveForm.name" placeholder="输入策略名" />
              </div>
              <div class="form-group">
                <label>分类</label>
                <select v-model="saveForm.category">
                  <option value="custom">自定义</option>
                  <option value="trend">趋势</option>
                  <option value="mean_reversion">均值回归</option>
                  <option value="momentum">动量</option>
                  <option value="breakout">突破</option>
                  <option value="volume">成交量</option>
                </select>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group grow">
                <label>说明</label>
                <input type="text" v-model="saveForm.description" placeholder="一句话描述这个策略" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group grow">
                <label>代码预览</label>
                <pre class="code-preview">{{ codeForm.code }}</pre>
              </div>
            </div>
            <div v-if="saveError" class="error-msg">{{ saveError }}</div>
          </div>
          <div class="modal-foot">
            <button class="btn-secondary" @click="saveDialogOpen = false">取消</button>
            <button class="btn-primary" :disabled="saving || !saveForm.name.trim()" @click="confirmSave">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
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

/* 币池选择 */
.pool-cfg { min-width: 280px; }
.pool-cfg label { display: flex; align-items: center; gap: 4px; }
.pool-count { color: var(--yellow); font-family: 'Consolas', monospace; }
.pool-picker { display: flex; flex-direction: column; gap: 6px; position: relative; }
.pool-toggle {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}
.pool-toggle.active {
  background: rgba(240,185,11,0.15);
  border-color: var(--yellow);
  color: var(--yellow);
}
.pool-toggle:hover:not(.active) { border-color: var(--yellow); }
.pool-toggle + .pool-toggle { margin-left: 4px; }
.pool-edit {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-muted);
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 11px;
  cursor: pointer;
  margin-left: 4px;
}
.pool-edit:hover { border-color: var(--yellow); color: var(--yellow); }
.pool-panel {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 50;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  width: 480px;
  max-width: 90vw;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  margin-top: 4px;
}
.pool-tools {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
}
.pool-search {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
  outline: none;
}
.pool-search:focus { border-color: var(--yellow); }
.pool-mini {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
}
.pool-mini:hover { border-color: var(--yellow); color: var(--yellow); }
.pool-hint { font-size: 11px; color: var(--text-muted); margin-left: auto; }
.pool-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  max-height: 280px;
  overflow-y: auto;
}
.pool-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  user-select: none;
  font-family: 'Consolas', monospace;
}
.pool-chip:hover { border-color: var(--yellow); }
.pool-chip.active {
  background: rgba(240,185,11,0.15);
  border-color: var(--yellow);
  color: var(--yellow);
}
.pool-chip input { margin: 0; accent-color: var(--yellow); }
.pool-sym { font-weight: 600; }
.pool-name {
  color: var(--text-secondary);
  font-family: inherit;
  font-size: 10px;
  margin-left: auto;
}
.pool-empty {
  grid-column: 1 / -1;
  text-align: center;
  padding: 20px;
  color: var(--text-muted);
  font-size: 12px;
}

/* 权重编辑 */
.weight-cfg { min-width: 240px; }
.weight-hint { color: var(--yellow); font-family: 'Consolas', monospace; font-size: 10px; font-weight: normal; margin-left: 4px; }
.weight-picker { display: flex; flex-direction: column; gap: 6px; position: relative; }
.weight-panel {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 50;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  width: 480px;
  max-width: 90vw;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  margin-top: 4px;
}
.weight-tools {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.weight-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 320px;
  overflow-y: auto;
}
.weight-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
}
.weight-row:hover { border-color: var(--yellow); }
.weight-sym {
  font-family: 'Consolas', monospace;
  font-weight: 600;
  min-width: 90px;
  color: var(--text);
}
.weight-input {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 3px 6px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  width: 70px;
  outline: none;
}
.weight-input:focus { border-color: var(--yellow); }
.weight-bar-wrap {
  flex: 1;
  height: 6px;
  background: var(--bg-elevated);
  border-radius: 3px;
  overflow: hidden;
  position: relative;
}
.weight-bar {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--yellow) 0%, rgba(240,185,11,0.5) 100%);
  transition: width 0.15s;
}
.weight-pct {
  font-family: 'Consolas', monospace;
  font-size: 11px;
  color: var(--text-secondary);
  min-width: 48px;
  text-align: right;
}
.weight-warn {
  margin-top: 8px;
  padding: 6px 10px;
  background: rgba(246,70,93,0.1);
  border: 1px solid var(--red);
  color: var(--red);
  border-radius: 4px;
  font-size: 11px;
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
.ranking-header h3 { font-size: 16px; display: flex; align-items: center; gap: 8px; }
.count-chip {
  background: var(--bg-elevated);
  color: var(--yellow);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
}
.ranking-tools { display: flex; align-items: center; gap: 12px; }
.symbol-search {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  width: 160px;
  outline: none;
}
.symbol-search:focus { border-color: var(--yellow); }
.btn-clear {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 11px;
}
.btn-clear:hover { border-color: var(--red); color: var(--red); }
.ranking-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin-bottom: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}
.chip-label { font-size: 11px; color: var(--text-muted); margin-right: 4px; }
.r-chip {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-family: 'Consolas', monospace;
  cursor: pointer;
  user-select: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.r-chip:hover { border-color: var(--yellow); color: var(--text); }
.r-chip.active {
  background: rgba(240,185,11,0.1);
  border-color: var(--yellow);
  color: var(--yellow);
}
.r-dot {
  width: 4px; height: 4px;
  background: currentColor;
  border-radius: 50%;
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
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
th.sortable { cursor: pointer; }
th.sortable:hover { color: var(--yellow); }
th.sortable .arr {
  display: inline-block;
  margin-left: 2px;
  font-size: 10px;
  color: var(--text-muted);
  font-weight: 700;
}
th.sortable .arr { color: var(--yellow); }
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
.code-toggle {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.code-toggle:hover { border-color: var(--yellow); }
.code-toggle.active {
  background: rgba(240,185,11,0.1);
  border-color: var(--yellow);
  color: var(--yellow);
}
.code-status {
  font-size: 12px;
  font-family: 'Consolas', monospace;
}
.code-status.ok { color: var(--green); }
.code-status.err { color: var(--red); }
.code-status .muted { color: var(--text-muted); }
.editor-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.editor-label { font-size: 12px; color: var(--text-secondary); }
.code-result-card h3 { font-size: 16px; margin-bottom: 12px; }
.code-result-card h4 { font-size: 14px; margin-bottom: 8px; color: var(--text-secondary); }
.slide-enter-active, .slide-leave-active { transition: opacity 0.2s, transform 0.2s; overflow: hidden; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(-8px); }

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
  width: 100%; max-width: 640px;
  max-height: 90vh;
  display: flex; flex-direction: column;
  box-shadow: 0 10px 40px rgba(0,0,0,0.4);
}
.modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.modal-head h3 { font-size: 16px; }
.modal-close {
  background: transparent;
  color: var(--text-muted);
  font-size: 24px;
  padding: 0 8px;
  line-height: 1;
}
.modal-close:hover { color: var(--red); }
.modal-body { padding: 16px 20px; overflow-y: auto; flex: 1; }
.modal-body .form-row {
  display: flex; gap: 12px; margin-bottom: 12px;
}
.modal-body .form-group { display: flex; flex-direction: column; gap: 4px; }
.modal-body .form-group.grow { flex: 1; }
.modal-body .form-group label { font-size: 12px; color: var(--text-secondary); }
.modal-body .form-group input, .modal-body .form-group select {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.modal-body .form-group input:focus, .modal-body .form-group select:focus { border-color: var(--yellow); outline: none; }
.code-preview {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--yellow);
  font-family: 'Consolas', monospace;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}
.modal-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}
.success-msg {
  background: rgba(2,192,118,0.1);
  border: 1px solid var(--green);
  color: var(--green);
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
  margin-bottom: 12px;
}
.error-msg {
  background: rgba(246,70,93,0.1);
  border: 1px solid var(--red);
  color: var(--red);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  margin-top: 8px;
}

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