<script setup>
import { ref, computed, watch } from 'vue'
import { getTimeframes } from '../api'

const props = defineProps({
  modelValue: String,
})
const emit = defineEmits(['update:modelValue', 'change'])

// 从后端拉 Binance 白名单 (后端是 source of truth)
const tfs = ref([])  // 全部 Binance tf
const groups = ref([])  // 按单位分组

async function loadTimeframes() {
  try {
    const r = await getTimeframes()
    const all = r?.data?.timeframes || []
    tfs.value = all
    groups.value = [
      { label: '秒',  unit: 's', tfs: all.filter(t => t.endsWith('s')) },
      { label: '分钟', unit: 'm', tfs: all.filter(t => t.endsWith('m')) },
      { label: '小时', unit: 'h', tfs: all.filter(t => t.endsWith('h')) },
      { label: '天',   unit: 'd', tfs: all.filter(t => t.endsWith('d')) },
      { label: '周',   unit: 'w', tfs: all.filter(t => t.endsWith('w')) },
      { label: '月',   unit: 'M', tfs: all.filter(t => t.endsWith('M')) },
    ].filter(g => g.tfs.length > 0)
  } catch (e) {
    // 兜底 (用本地 Binance 白名单)
    tfs.value = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '1w']
    groups.value = [
      { label: '分钟', unit: 'm', tfs: ['1m', '5m', '15m', '30m'] },
      { label: '小时', unit: 'h', tfs: ['1h', '2h', '4h', '6h', '12h'] },
      { label: '天',   unit: 'd', tfs: ['1d'] },
      { label: '周',   unit: 'w', tfs: ['1w'] },
    ]
  }
}
loadTimeframes()

const PRESETS = computed(() => new Set(tfs.value))

// 自定义功能: 提示用户必须从 Binance 白名单选 (后端拒绝任意 tf)
const showCustom = ref(false)
const customValue = ref('')  // 用户输入的 tf 字符串

watch(() => props.modelValue, (v) => {
  if (!v) return
  if (PRESETS.value.has(v)) {
    showCustom.value = false
  } else {
    showCustom.value = true
    customValue.value = v
  }
}, { immediate: true })

function select(tf) {
  showCustom.value = false
  emit('update:modelValue', tf)
  emit('change', tf)
}

function isValidCustom(v) {
  return PRESETS.value.has(v)
}

function applyCustom() {
  if (!isValidCustom(customValue.value)) return
  emit('update:modelValue', customValue.value)
  emit('change', customValue.value)
}
</script>

<template>
  <div class="tf-picker">
    <span class="lbl">K线</span>
    <div v-for="g in groups" :key="g.label" class="group">
      <span class="glbl">{{ g.label }}</span>
      <button v-for="tf in g.tfs" :key="tf"
        :class="{ active: modelValue === tf && !showCustom }"
        @click="select(tf)" :title="tf">{{ tf }}</button>
    </div>
    <div class="group custom-grp">
      <button class="custom-btn" :class="{ active: showCustom }"
        @click="showCustom = !showCustom" title="查看/输入自定义 Binance 周期">自定义</button>
      <div v-if="showCustom" class="custom-editor">
        <input type="text" v-model="customValue" placeholder="如 4h / 15m"
          @keyup.enter="applyCustom" />
        <span v-if="customValue && !isValidCustom(customValue)" class="err">
          ✗ 非 Binance 周期
        </span>
        <span v-else-if="customValue" class="ok">✓</span>
        <button class="apply" :disabled="!isValidCustom(customValue)"
          @click="applyCustom">应用</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tf-picker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 8px;
}
.lbl { font-size: 11px; color: var(--text-secondary); padding: 0 4px; white-space: nowrap; }
.group {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  padding: 0 4px;
  border-right: 1px solid var(--border);
}
.group:last-child { border-right: 0; }
.glbl {
  font-size: 10px;
  color: var(--text-muted);
  margin-right: 2px;
  user-select: none;
}
.group button {
  background: transparent;
  color: var(--text-secondary);
  padding: 3px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-family: 'Consolas', monospace;
}
.group button:hover { color: var(--text); background: var(--bg-elevated); }
.group button.active {
  background: var(--yellow);
  color: #000;
  font-weight: 600;
}
.custom-grp { position: relative; }
.custom-btn { font-weight: 600; }
.custom-editor {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.custom-editor input {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 4px 6px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  width: 100px;
}
.custom-editor input:focus { border-color: var(--yellow); outline: none; }
.custom-editor .apply {
  background: var(--yellow);
  color: #000;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
}
.custom-editor .apply:disabled {
  background: var(--bg-elevated);
  color: var(--text-muted);
  cursor: not-allowed;
}
.custom-editor .err { color: var(--red); font-size: 11px; }
.custom-editor .ok { color: var(--green); font-size: 13px; font-weight: 600; }
</style>
