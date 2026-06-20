<script setup>
import { ref, computed } from 'vue'
import { setActiveSymbols } from '../api'

const props = defineProps({ cfg: Object, reload: Function })

const activeSet = ref(new Set(props.cfg?.settings?.active_symbols || []))
const selectedDetail = ref(props.cfg?.symbols?.[0]?.symbol || null)
const saving = ref(false)
const msg = ref('')

const allSymbols = computed(() => props.cfg?.symbols || [])
const activeList = computed(() => allSymbols.value.filter(s => activeSet.value.has(s.symbol)))
const detail = computed(() => allSymbols.value.find(s => s.symbol === selectedDetail.value))

const CATEGORY_LABEL = {
  layer1: 'Layer 1 公链', layer2: 'Layer 2', layer0: '跨链/L0',
  defi: 'DeFi', meme: 'Meme 币', payment: '支付',
  exchange: '交易所', oracle: '预言机', ai: 'AI 概念',
  modular: '模块化', other: '其他',
}

function toggle(symbol) {
  if (activeSet.value.has(symbol)) activeSet.value.delete(symbol)
  else activeSet.value.add(symbol)
}

async function save() {
  saving.value = true
  msg.value = ''
  try {
    await setActiveSymbols([...activeSet.value])
    msg.value = '✓ 已保存'
    await props.reload?.()
    setTimeout(() => msg.value = '', 2000)
  } catch (e) {
    msg.value = '✗ ' + e.message
  } finally {
    saving.value = false
  }
}

const sortedSymbols = computed(() => {
  return [...allSymbols.value].sort((a, b) =>
    (a.market_cap_rank || 999) - (b.market_cap_rank || 999))
})
</script>

<template>
  <div class="symbols-view">
    <div class="config-card">
      <div class="card-header">
        <div>
          <h3>活跃币种池</h3>
          <p class="hint">选中的币种会在「智能回测」「筛选」中作为默认池。点击保存后生效。</p>
        </div>
        <div class="header-actions">
          <span class="count">{{ activeSet.size }} / {{ allSymbols.length }}</span>
          <button class="save-btn" :disabled="saving" @click="save">
            {{ saving ? '保存中...' : '保存' }}
          </button>
          <span v-if="msg" class="msg">{{ msg }}</span>
        </div>
      </div>
      <div class="symbol-grid">
        <button v-for="s in sortedSymbols" :key="s.symbol"
          :class="['sym-btn', { active: activeSet.has(s.symbol) }]"
          @click="toggle(s.symbol)">
          <div class="sym-top">
            <span class="rank">#{{ s.market_cap_rank }}</span>
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
        <span class="badge rank">市值排名 #{{ detail.market_cap_rank }}</span>
      </div>
      <p class="detail-desc">{{ detail.description }}</p>
      <div class="detail-tags">
        <span v-for="t in detail.tags" :key="t" class="tag">#{{ t }}</span>
      </div>
      <div class="detail-actions">
        <button :class="['detail-btn', { active: activeSet.has(detail.symbol) }]"
          @click="toggle(detail.symbol)">
          {{ activeSet.has(detail.symbol) ? '✓ 已加入活跃池' : '+ 加入活跃池' }}
        </button>
        <button class="detail-btn outline" @click="selectedDetail = null">关闭</button>
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
.symbols-view { display: flex; flex-direction: column; gap: 16px; }
.config-card, .detail-card, .active-list-card {
  background: var(--binance-card);
  border: 1px solid var(--binance-border);
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
.card-header .hint { font-size: 12px; color: var(--binance-text-secondary); }
.header-actions { display: flex; align-items: center; gap: 12px; }
.count {
  background: #f0b90b22;
  color: var(--binance-yellow);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
.save-btn {
  background: var(--binance-yellow);
  color: #0b0e11;
  padding: 8px 20px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 13px;
}
.save-btn:disabled { opacity: 0.6; }
.msg { font-size: 13px; color: var(--binance-green); }

.symbol-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.sym-btn {
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  padding: 12px;
  border-radius: 8px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
}
.sym-btn:hover { border-color: var(--binance-yellow); }
.sym-btn.active {
  background: #f0b90b11;
  border-color: var(--binance-yellow);
}
.sym-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.sym-top .rank {
  font-size: 10px;
  color: var(--binance-text-secondary);
  font-family: 'Consolas', monospace;
}
.sym-top .check { color: var(--binance-yellow); font-size: 14px; font-weight: 700; }
.sym-name { font-size: 14px; font-weight: 600; color: var(--binance-text); margin-bottom: 2px; }
.sym-code { font-size: 11px; color: var(--binance-yellow); font-family: 'Consolas', monospace; margin-bottom: 4px; }
.sym-cat {
  font-size: 10px;
  color: var(--binance-text-secondary);
  background: #2b3139;
  padding: 2px 6px;
  border-radius: 3px;
  display: inline-block;
}

.detail-card h3 { font-size: 22px; color: var(--binance-yellow); margin-bottom: 12px; }
.detail-card .en { font-size: 14px; color: var(--binance-text-secondary); font-weight: 400; margin-left: 8px; }
.detail-meta { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.badge {
  background: #2b3139;
  color: var(--binance-text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
}
.badge.cat { background: #1e88e522; color: #64b5f6; }
.badge.rank { background: #f0b90b22; color: var(--binance-yellow); }
.detail-desc {
  font-size: 13px;
  color: var(--binance-text-secondary);
  line-height: 1.8;
  margin-bottom: 16px;
  white-space: pre-line;
}
.detail-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
.tag {
  background: #0b0e11;
  color: var(--binance-yellow);
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 11px;
}
.detail-actions { display: flex; gap: 8px; }
.detail-btn {
  background: var(--binance-yellow);
  color: #0b0e11;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
}
.detail-btn.outline {
  background: transparent;
  color: var(--binance-text-secondary);
  border: 1px solid var(--binance-border);
}

.active-list-card h3 { font-size: 16px; margin-bottom: 12px; }
.active-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
}
.active-item {
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  padding: 8px 12px;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: all 0.2s;
}
.active-item:hover { border-color: var(--binance-yellow); }
.active-item .sym { font-family: 'Consolas', monospace; color: var(--binance-yellow); font-weight: 600; font-size: 12px; }
.active-item .name { color: var(--binance-text-secondary); font-size: 11px; flex: 1; margin: 0 8px; }
.active-item .rm {
  background: transparent;
  color: #f6465d;
  font-size: 16px;
  padding: 0 6px;
}
.active-item .rm:hover { color: #ff7b72; }
</style>