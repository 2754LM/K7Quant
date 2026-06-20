<script setup>
import { ref, computed, watch, onMounted } from 'vue'

const props = defineProps({
  start: String,        // YYYYMMDD
  end: String,
  defaultRange: { type: String, default: '3m' },
})
const emit = defineEmits(['update:start', 'update:end', 'change'])

// YYYYMMDD <-> YYYY-MM-DD
function toIso(s) {
  if (!s || s.length !== 8) return ''
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
}
function fromIso(s) {
  if (!s || s.length !== 10) return ''
  return s.replace(/-/g, '')
}

const startIso = computed({
  get: () => toIso(props.start),
  set: (v) => emit('update:start', fromIso(v)),
})
const endIso = computed({
  get: () => toIso(props.end),
  set: (v) => emit('update:end', fromIso(v)),
})

const RANGES = [
  { id: '1w', label: '1周', days: 7 },
  { id: '1m', label: '1月', days: 30 },
  { id: '3m', label: '3月', days: 90 },
  { id: '6m', label: '6月', days: 180 },
  { id: '1y', label: '1年', days: 365 },
  { id: '2y', label: '2年', days: 730 },
  { id: 'all', label: '全部', days: null },
]

const activeRange = ref(props.defaultRange)
const inited = ref(false)

function setRange(r) {
  activeRange.value = r.id
  const now = new Date()
  const end = fromIso(now.toISOString().slice(0, 10))
  let start
  if (r.days) {
    const d = new Date(now)
    d.setDate(d.getDate() - r.days)
    start = fromIso(d.toISOString().slice(0, 10))
  } else {
    start = '20170101'
  }
  emit('update:start', start)
  emit('update:end', end)
  emit('change', { start, end })
}

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

onMounted(() => {
  if (!props.start || !props.end) {
    setRange(RANGES.find(r => r.id === props.defaultRange) || RANGES[2])
  }
  inited.value = true
})
</script>

<template>
  <div class="date-picker">
    <div class="presets">
      <button v-for="r in RANGES" :key="r.id"
        :class="{ active: activeRange === r.id }"
        @click="setRange(r)">{{ r.label }}</button>
    </div>
    <div class="inputs">
      <input type="date" v-model="startIso" :max="endIso || todayIso()" />
      <span class="sep">→</span>
      <input type="date" v-model="endIso" :min="startIso" :max="todayIso()" />
    </div>
  </div>
</template>

<style scoped>
.date-picker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.presets {
  display: flex;
  gap: 2px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 3px 6px;
}
.presets button {
  background: transparent;
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
}
.presets button:hover { color: var(--text); }
.presets button.active {
  background: var(--yellow);
  color: #000;
  font-weight: 600;
}
.inputs {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.inputs input {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  color-scheme: dark;
}
.inputs input:focus { border-color: var(--yellow); outline: none; }
.sep { color: var(--text-muted); font-size: 14px; }
</style>
