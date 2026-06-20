<script setup>
defineProps({
  label: String,
  value: [String, Number, Boolean],
  fmt: { type: String, default: 'auto' },
  highlight: Boolean,
  sub: String,
  help: String,
})

import HelpTip from './HelpTip.vue'

function format(v, fmt) {
  if (v === null || v === undefined || v === '-') return '-'
  if (fmt === 'pct' || (fmt === 'auto' && typeof v === 'number' && Math.abs(v) < 100)) {
    const n = Number(v)
    if (!isNaN(n)) return (n * 100).toFixed(2) + '%'
  }
  if (fmt === 'num') return Number(v).toFixed(2)
  return String(v)
}
</script>

<template>
  <div class="card" :class="{ highlight }">
    <div class="label">
      {{ label }}
      <HelpTip v-if="help" :text="help" />
    </div>
    <div class="value" :class="{
      pos: Number(value) > 0,
      neg: Number(value) < 0,
    }">{{ format(value, fmt) }}</div>
    <div v-if="sub" class="sub">{{ sub }}</div>
  </div>
</template>

<style scoped>
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
}
.card.highlight {
  background: linear-gradient(135deg, rgba(240,185,11,0.08), transparent);
  border-color: rgba(240,185,11,0.3);
}
.label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
}
.value {
  font-size: 20px;
  font-weight: 700;
  font-family: 'Consolas', 'Monaco', monospace;
  line-height: 1.2;
}
.value.pos { color: var(--green); }
.value.neg { color: var(--red); }
.sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}
</style>