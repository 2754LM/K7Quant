<script setup>
import { ref, computed, inject } from 'vue'
import { filterSymbols, getStrategies } from '../api'

import StateView from '../components/StateView.vue'
import DateRangePicker from '../components/DateRangePicker.vue'
import TimeframePicker from '../components/TimeframePicker.vue'

const cfg = inject('cfg')

const params = ref({
  strategy_id: null,
  timeframe: '1d',
  start_date: '20240101', end_date: '20250601',
  min_return: -1.0, max_return: 100.0,
  min_price: 0, max_price: 1e12,
  min_sharpe: 0,
})

const results = ref([])
const loading = ref(false)
const error = ref('')
const count = ref(0)

const strategies = computed(() => cfg.value?.strategies || [])
const timeframes = computed(() => cfg.value?.timeframes || ['1d'])

const presets = [
  { name: '🚀 牛市赢家', patch: { min_return: 0.5, min_sharpe: 0.5 } },
  { name: '🛡️ 防御币种', patch: { min_return: -0.3, max_return: 0.3, min_sharpe: 0 } },
  { name: '💎 高夏普', patch: { min_return: -0.3, min_sharpe: 1 } },
  { name: '🐋 低价币 (< $1)', patch: { max_price: 1 } },
  { name: '💰 中价币 ($1-$100)', patch: { min_price: 1, max_price: 100 } },
  { name: '🏔️ 高价币 (> $1000)', patch: { min_price: 1000 } },
]

const symbolInfo = computed(() => {
  const m = {}
  for (const s of cfg.value?.symbols || []) m[s.symbol] = s
  return m
})

async function run() {
  loading.value = true
  error.value = ''
  try {
    const res = await filterSymbols(params.value)
    results.value = res.data.results
    count.value = res.data.count
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function applyPreset(p) {
  Object.assign(params.value, p.patch)
  run()
}

function fmt(v) { return v === null || v === undefined ? '-' : Number(v).toFixed(2) }
</script>

<template>
  <div class="filter-view">
    <div class="preset-bar">
      <span class="preset-label">快速场景:</span>
      <button v-for="p in presets" :key="p.name" @click="applyPreset(p)" class="preset-btn">
        {{ p.name }}
      </button>
    </div>

    <div class="config-card">
      <h3>筛选条件</h3>
      <div class="form-grid">
        <div class="form-row">
          <label>策略 (可选)</label>
          <select v-model="params.strategy_id">
            <option :value="null">无 (按涨幅+价格)</option>
            <option v-for="s in strategies" :key="s.id" :value="s.id">
              {{ s.name }}
            </option>
          </select>
        </div>
        <div class="form-row">
          <label>K线</label>
          <TimeframePicker :timeframes="timeframes" v-model="params.timeframe" />
        </div>
        <div class="form-row">
          <label>区间最低涨幅</label>
          <input type="number" v-model.number="params.min_return" step="0.1" />
          <span class="hint">-1=跌100%, 0.5=涨50%</span>
        </div>
        <div class="form-row">
          <label>区间最高涨幅</label>
          <input type="number" v-model.number="params.max_return" step="1" />
          <span class="hint">避免过热</span>
        </div>
        <div class="form-row">
          <label>最低价格</label>
          <input type="number" v-model.number="params.min_price" step="0.1" />
        </div>
        <div class="form-row">
          <label>最高价格</label>
          <input type="number" v-model.number="params.max_price" step="100" />
        </div>
        <div class="form-row">
          <label>最低夏普</label>
          <input type="number" v-model.number="params.min_sharpe" step="0.1" />
          <span class="hint">&gt;1 优秀, &gt;0 正期望</span>
        </div>
        <div class="form-row" style="grid-column: span 3">
          <label>日期区间</label>
          <DateRangePicker v-model:start="params.start_date" v-model:end="params.end_date" default-range="3m" />
        </div>
      </div>
      <button class="btn-primary" @click="run" :disabled="loading">
        {{ loading ? '筛选中...' : '开始筛选' }}
      </button>
    </div>

    <div v-if="results.length" class="results-card">
      <div class="results-header">
        <h3>筛选结果 ({{ count }} 个)</h3>
      </div>
      <table>
        <thead>
          <tr>
            <th>#</th><th>币种</th><th>名称</th><th>分类</th>
            <th>当前价</th><th>区间涨跌</th><th>夏普</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in results" :key="r.symbol" :class="{ top: i < 3 }">
            <td>{{ i + 1 }}</td>
            <td class="sym-cell">{{ r.symbol }}</td>
            <td class="name-cell">{{ symbolInfo[r.symbol]?.name_zh || '—' }}</td>
            <td><span class="cat-badge">{{ symbolInfo[r.symbol]?.category || '—' }}</span></td>
            <td>${{ fmt(r.last_close) }}</td>
            <td :class="r.period_return >= 0 ? 'pos' : 'neg'">{{ fmt(r.period_return) }}%</td>
            <td :class="r.sharpe >= 1 ? 'pos' : r.sharpe < 0 ? 'neg' : ''">
              {{ r.sharpe !== null && r.sharpe !== undefined ? fmt(r.sharpe) : '—' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <StateView :loading="loading" :error="error" empty-text="点击「开始筛选」" empty-icon="🔍"
      v-if="!results.length && !loading && !error" />
  </div>
</template>

<style scoped>
.filter-view { display: flex; flex-direction: column; gap: 16px; }
.preset-bar {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 16px;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.preset-label { font-size: 13px; color: var(--text-secondary); }
.preset-btn {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 6px 14px;
  border-radius: 16px;
  font-size: 13px;
}
.preset-btn:hover { background: var(--bg-elevated); border-color: var(--yellow); }
.config-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.config-card h3 { font-size: 16px; margin-bottom: 16px; }
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row label { font-size: 12px; color: var(--text-secondary); }
.form-row input, .form-row select {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.form-row input:focus, .form-row select:focus { border-color: var(--yellow); }
.form-row .hint { font-size: 11px; color: var(--text-muted); }
.results-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.results-header h3 { font-size: 16px; margin-bottom: 12px; }
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left;
  padding: 10px 12px;
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  border-bottom: 1px solid var(--border);
}
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
tr.top { background: rgba(240,185,11,0.04); }
tr:hover td { background: var(--bg-elevated); }
.sym-cell { font-weight: 600; color: var(--yellow); }
.name-cell { color: var(--text-secondary); font-family: inherit; font-size: 12px; }
.cat-badge {
  background: rgba(30,136,229,0.15);
  color: #64b5f6;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-family: inherit;
}
.pos { color: var(--green); }
.neg { color: var(--red); }

@media (max-width: 900px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>