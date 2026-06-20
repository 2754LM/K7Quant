<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { listSymbols, setActiveSymbols, listExchangeSymbols } from '../api'

import StateView from '../components/StateView.vue'

const cfg = inject('cfg')
const reloadCfg = inject('reload')

const symbols = ref([])
const exchangeSymbols = ref([])
const loading = ref(false)
const error = ref('')
const activeSet = ref(new Set())
const selectedDetail = ref(null)
const search = ref('')

const filtered = computed(() => {
  if (!search.value) return symbols.value
  const s = search.value.toLowerCase()
  return symbols.value.filter(x =>
    x.symbol.toLowerCase().includes(s) ||
    (x.name_zh || '').includes(s) ||
    (x.name_en || '').toLowerCase().includes(s)
  )
})

const detail = computed(() => symbols.value.find(s => s.symbol === selectedDetail.value))
const activeList = computed(() => symbols.value.filter(s => activeSet.value.has(s.symbol)))

const CATEGORY_LABEL = {
  layer1: 'L1 公链', layer2: 'L2', layer0: 'L0 跨链',
  defi: 'DeFi', meme: 'Meme', payment: '支付',
  exchange: '交易所', oracle: '预言机', ai: 'AI 概念',
  modular: '模块化', other: '其他',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await listSymbols(false)
    symbols.value = res.data.symbols
    activeSet.value = new Set(symbols.value.filter(s => s.is_active).map(s => s.symbol))
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadExchange() {
  try {
    const res = await listExchangeSymbols()
    exchangeSymbols.value = res.data.symbols
  } catch {}
}

function toggle(symbol) {
  if (activeSet.value.has(symbol)) activeSet.value.delete(symbol)
  else activeSet.value.add(symbol)
}

async function save() {
  try {
    await setActiveSymbols([...activeSet.value])
    if (reloadCfg) await reloadCfg()
    alert('已保存')
  } catch (e) {
    alert('保存失败: ' + e.message)
  }
}

onMounted(() => {
  load()
  loadExchange()
})
</script>

<template>
  <div class="symbols-page">
    <div class="config-card">
      <div class="card-header">
        <div>
          <h3>活跃币种池</h3>
          <p class="hint">选中的币种在「智能回测」「筛选」中作为默认池</p>
        </div>
        <div class="header-actions">
          <span class="count">{{ activeSet.size }} / {{ symbols.length }}</span>
          <button class="btn-primary" @click="save">保存</button>
        </div>
      </div>
      <div class="search-bar">
        <input v-model="search" type="text" placeholder="搜索币种 (代码/中文/英文)" />
      </div>
      <StateView :loading="loading" :error="error" />
      <div v-if="!loading && !error" class="symbol-grid">
        <button v-for="s in filtered" :key="s.symbol"
          :class="['sym-btn', { active: activeSet.has(s.symbol) }]"
          @click="toggle(s.symbol)">
          <div class="sym-top">
            <span class="rank">#{{ s.market_cap_rank || '?' }}</span>
            <span v-if="activeSet.has(s.symbol)" class="check">✓</span>
          </div>
          <div class="sym-name">{{ s.name_zh }}</div>
          <div class="sym-code">{{ s.symbol }}</div>
          <div class="sym-cat">{{ CATEGORY_LABEL[s.category] || s.category }}</div>
        </button>
      </div>
    </div>

    <div class="detail-card" v-if="detail">
      <h3>{{ detail.name_zh }} <span class="en">({{ detail.name_en }})</span></h3>
      <div class="detail-meta">
        <span class="badge">{{ detail.symbol }}</span>
        <span class="badge cat">{{ CATEGORY_LABEL[detail.category] || detail.category }}</span>
        <span class="badge rank">市值 #{{ detail.market_cap_rank }}</span>
      </div>
      <p class="detail-desc">{{ detail.description }}</p>
      <div class="detail-tags">
        <span v-for="t in detail.tags" :key="t" class="tag">#{{ t }}</span>
      </div>
      <div class="detail-actions">
        <button :class="['btn-primary', { active: activeSet.has(detail.symbol) }]"
          @click="toggle(detail.symbol)">
          {{ activeSet.has(detail.symbol) ? '✓ 已在活跃池' : '+ 加入活跃池' }}
        </button>
        <button class="btn-secondary" @click="selectedDetail = null">关闭</button>
      </div>
    </div>

    <div class="active-list-card" v-if="activeList.length">
      <h3>当前活跃币种 ({{ activeList.length }})</h3>
      <div class="active-grid">
        <div v-for="s in activeList" :key="s.symbol" class="active-item" @click="selectedDetail = s.symbol">
          <div class="sym">{{ s.symbol }}</div>
          <div class="name">{{ s.name_zh }}</div>
          <button class="rm" @click.stop="toggle(s.symbol)">×</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.symbols-page { display: flex; flex-direction: column; gap: 16px; }
.config-card, .detail-card, .active-list-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px 24px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.card-header h3 { font-size: 16px; margin-bottom: 4px; }
.card-header .hint { font-size: 12px; color: var(--text-secondary); }
.header-actions { display: flex; align-items: center; gap: 12px; }
.count {
  background: rgba(240,185,11,0.15);
  color: var(--yellow);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
.search-bar { margin-bottom: 16px; }
.search-bar input {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 14px;
}
.symbol-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.sym-btn {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 12px;
  border-radius: 8px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
}
.sym-btn:hover { border-color: var(--yellow); }
.sym-btn.active {
  background: rgba(240,185,11,0.1);
  border-color: var(--yellow);
}
.sym-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.sym-top .rank {
  font-size: 10px;
  color: var(--text-secondary);
  font-family: 'Consolas', monospace;
}
.sym-top .check { color: var(--yellow); font-size: 14px; font-weight: 700; }
.sym-name { font-size: 14px; font-weight: 600; }
.sym-code { font-size: 11px; color: var(--yellow); font-family: 'Consolas', monospace; margin: 2px 0 4px; }
.sym-cat {
  font-size: 10px;
  color: var(--text-secondary);
  background: var(--bg-elevated);
  padding: 2px 6px;
  border-radius: 3px;
  display: inline-block;
}
.detail-card h3 { font-size: 22px; color: var(--yellow); margin-bottom: 12px; }
.detail-card .en { font-size: 14px; color: var(--text-secondary); font-weight: 400; margin-left: 8px; }
.detail-meta { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.badge {
  background: var(--bg-elevated);
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
}
.badge.cat { background: rgba(30,136,229,0.15); color: #64b5f6; }
.badge.rank { background: rgba(240,185,11,0.15); color: var(--yellow); }
.detail-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
  margin-bottom: 16px;
  white-space: pre-line;
}
.detail-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
.tag {
  background: var(--bg);
  color: var(--yellow);
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 11px;
}
.detail-actions { display: flex; gap: 8px; }
.btn-primary.active { background: var(--green); color: #fff; }
.active-list-card h3 { font-size: 16px; margin-bottom: 12px; }
.active-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
}
.active-item {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 8px 12px;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
}
.active-item:hover { border-color: var(--yellow); }
.active-item .sym { font-family: 'Consolas', monospace; color: var(--yellow); font-weight: 600; font-size: 12px; }
.active-item .name { color: var(--text-secondary); font-size: 11px; flex: 1; margin: 0 8px; }
.active-item .rm {
  background: transparent;
  color: var(--red);
  font-size: 16px;
  padding: 0 6px;
}
</style>