<script setup>
defineProps({
  label: String,
  value: [String, Number],
  fmt: { type: String, default: 'auto' }, // pct | num | raw
  highlight: Boolean,
  sub: String,
})

function format(v, fmt) {
  if (v === null || v === undefined || v === '-') return '-'
  if (fmt === 'pct' || fmt === 'auto') {
    const n = Number(v)
    if (!isNaN(n) && Math.abs(n) < 10) return (n * 100).toFixed(2) + '%'
  }
  if (fmt === 'num') return Number(v).toFixed(2)
  return String(v)
}
</script>

<template>
  <div class="card" :class="{ highlight }">
    <div class="label">{{ label }}</div>
    <div class="value" :class="{
      pos: Number(value) > 0,
      neg: Number(value) < 0,
    }">{{ format(value, fmt) }}</div>
    <div v-if="sub" class="sub">{{ sub }}</div>
  </div>
</template>

<style scoped>
.card {
  background: var(--binance-card);
  border: 1px solid var(--binance-border);
  border-radius: 10px;
  padding: 14px 16px;
  position: relative;
  overflow: hidden;
}
.card.highlight {
  background: linear-gradient(135deg, #f0b90b11, transparent);
  border-color: #f0b90b44;
}
.label {
  font-size: 11px;
  color: var(--binance-text-secondary);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.value {
  font-size: 22px;
  font-weight: 700;
  font-family: 'Consolas', 'Monaco', monospace;
  line-height: 1.2;
}
.value.pos { color: var(--binance-green); }
.value.neg { color: var(--binance-red); }
.sub {
  font-size: 11px;
  color: var(--binance-text-secondary);
  margin-top: 4px;
}
</style>