<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { NDatePicker } from 'naive-ui'

const props = defineProps({
  start: String,        // YYYYMMDD
  end: String,
  defaultRange: { type: String, default: '1m' },
  timeframe: { type: String, default: null },  // 智能默认: 根据 tf 自动选
  size: { type: String, default: 'small' },
})
const emit = defineEmits(['update:start', 'update:end', 'change'])

// 内部用 Naive UI 的 timestamp (ms) 表示
const tsStart = computed({
  get: () => toTs(props.start),
  set: (v) => emit('update:start', fromTs(v)),
})
const tsEnd = computed({
  get: () => toTs(props.end),
  set: (v) => emit('update:end', fromTs(v)),
})

function toTs(s) {
  if (!s || s.length !== 8) return null
  const y = +s.slice(0, 4), m = +s.slice(4, 6) - 1, d = +s.slice(6, 8)
  return new Date(y, m, d).getTime()
}
function fromTs(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
}

const RANGES = [
  { id: '1w', label: '1周', days: 7 },
  { id: '1m', label: '1月', days: 30 },
  { id: '3m', label: '3月', days: 90 },
  { id: '6m', label: '6月', days: 180 },
  { id: '1y', label: '1年', days: 365 },
  { id: '2y', label: '2年', days: 730 },
  { id: 'all', label: '全部', days: null },
]

// 根据 timeframe 选默认区间 (避免一次拉太多数据, 拖慢首屏)
function smartRangeFor(tf) {
  if (!tf) return '1m'
  if (['1m', '3m', '5m'].includes(tf)) return '1w'   // 分钟级 1 周够看
  if (['15m', '30m'].includes(tf)) return '1m'        // 15m/30m 1 个月
  if (['1h', '2h', '4h', '6h', '12h'].includes(tf)) return '3m'  // 小时级 3 个月
  if (['1d', '3d'].includes(tf)) return '6m'          // 日级 6 个月
  if (tf === '1w') return '2y'                        // 周级 2 年
  return '3m'
}

const activeRange = ref(props.defaultRange)

function setRange(r) {
  activeRange.value = r.id
  const now = new Date()
  let start
  if (r.days) {
    const d = new Date(now)
    d.setDate(d.getDate() - r.days)
    start = fromTs(d.getTime())
  } else {
    start = '20170101'
  }
  const end = fromTs(now.getTime())
  emit('update:start', start)
  emit('update:end', end)
  emit('change', { start, end })
}

onMounted(() => {
  if (!props.start || !props.end) {
    // 优先用 timeframe 智能选择, 然后才是 defaultRange
    const tfDefault = smartRangeFor(props.timeframe)
    const rangeId = props.timeframe ? tfDefault : (props.defaultRange || '1m')
    setRange(RANGES.find(r => r.id === rangeId) || RANGES[1])
  }
})

// 当 timeframe 变化时, 主动重置 (但只在没手动选过其他预设时)
watch(() => props.timeframe, (tf) => {
  if (!tf) return
  // 不主动改, 让用户自己选; 但可以提示
  // 暂时不重置, 避免误操作
})

watch([tsStart, tsEnd], ([s, e]) => {
  if (s && e) {
    emit('change', { start: fromTs(s), end: fromTs(e) })
    // 标记自定义区间 (不属于预设)
    const start = fromTs(s)
    const end = fromTs(e)
    if (!isPresetRange(start, end)) activeRange.value = ''
  }
})

function isPresetRange(start, end) {
  const now = new Date()
  const e = fromTs(now.getTime())
  if (end !== e) return false
  for (const r of RANGES) {
    if (!r.days) continue
    const d = new Date(now)
    d.setDate(d.getDate() - r.days)
    if (fromTs(d.getTime()) === start) return true
  }
  return false
}
</script>

<template>
  <div class="date-picker">
    <div class="presets">
      <button v-for="r in RANGES" :key="r.id"
        :class="{ active: activeRange === r.id }"
        @click="setRange(r)">{{ r.label }}</button>
    </div>
    <n-date-picker
      v-model:value="tsStart"
      type="date"
      :size="size"
      clearable
      placeholder="开始日期"
      style="width: 140px"
    />
    <span class="sep">→</span>
    <n-date-picker
      v-model:value="tsEnd"
      type="date"
      :size="size"
      clearable
      placeholder="结束日期"
      style="width: 140px"
    />
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
.sep { color: var(--text-muted); font-size: 14px; }
</style>
