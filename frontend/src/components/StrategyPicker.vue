<script setup>
import { computed } from 'vue'

const props = defineProps({
  strategies: Array,
  modelValue: [String, Number],
})
const emit = defineEmits(['update:modelValue', 'change'])

function select(id) {
  emit('update:modelValue', id)
  emit('change', id)
}

const CATEGORY_ZH = {
  trend: '趋势',
  mean_reversion: '均值回归',
  momentum: '动量',
  breakout: '突破',
  volume: '成交量',
  custom: '自定义',
}

const CATEGORY_ICON = {
  trend: '📈',
  mean_reversion: '🔁',
  momentum: '🚀',
  breakout: '💥',
  volume: '📊',
  custom: '✨',
}

function tooltipText(s) {
  // 拼接: 描述 + 各参数 hint
  let txt = s.description || s.name
  if (s.params_schema) {
    const params = Object.entries(s.params_schema)
      .map(([k, v]) => `${v.label || k}${v.unit ? `(${v.unit})` : ''}: ${v.hint || ''}`)
      .join('\n')
    if (params) txt += `\n\n参数说明:\n${params}`
  }
  return txt
}
</script>

<template>
  <div class="picker">
    <button v-for="s in strategies" :key="s.id"
      :class="{ active: modelValue === s.id }"
      @click="select(s.id)"
      :title="tooltipText(s)">
      <span class="icon">{{ s.icon || CATEGORY_ICON[s.category] || '📊' }}</span>
      <span class="name">{{ s.name }}</span>
      <span class="cat-tag" :data-cat="s.category">{{ CATEGORY_ZH[s.category] || s.category }}</span>
    </button>
  </div>
</template>

<style scoped>
.picker { display: flex; gap: 6px; flex-wrap: wrap; }
.picker button {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 6px 12px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  transition: all 0.2s;
}
.picker button:hover {
  border-color: var(--yellow);
  color: var(--text);
}
.picker button.active {
  background: rgba(240,185,11,0.1);
  border-color: var(--yellow);
  color: var(--yellow);
}
.icon { font-size: 14px; }
.name { font-weight: 500; }
.cat-tag {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 8px;
  background: var(--bg-elevated);
  color: var(--text-muted);
  font-weight: 400;
  margin-left: 2px;
}
.picker button.active .cat-tag {
  background: rgba(240,185,11,0.2);
  color: var(--yellow);
}
.cat-tag[data-cat="trend"] { background: rgba(46,204,113,0.15); color: #58d68d; }
.cat-tag[data-cat="mean_reversion"] { background: rgba(155,89,182,0.15); color: #bb8fce; }
.cat-tag[data-cat="momentum"] { background: rgba(241,196,15,0.15); color: #f4d03f; }
.cat-tag[data-cat="breakout"] { background: rgba(230,126,34,0.15); color: #f5b041; }
.cat-tag[data-cat="volume"] { background: rgba(26,188,156,0.15); color: #5dcead; }
.cat-tag[data-cat="custom"] { background: rgba(243,104,224,0.15); color: #f195d8; }
</style>
