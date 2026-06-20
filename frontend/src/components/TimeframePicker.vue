<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  modelValue: String,
})
const emit = defineEmits(['update:modelValue', 'change'])

// 预置按单位分组, 给每个加中文标签
const GROUPS = [
  {
    label: '分钟', unit: 'm',
    options: [
      { v: '1m', label: '1分' }, { v: '3m', label: '3分' }, { v: '5m', label: '5分' },
      { v: '15m', label: '15分' }, { v: '30m', label: '30分' },
    ],
  },
  {
    label: '小时', unit: 'h',
    options: [
      { v: '1h', label: '1时' }, { v: '2h', label: '2时' }, { v: '4h', label: '4时' },
      { v: '6h', label: '6时' }, { v: '12h', label: '12时' },
    ],
  },
  {
    label: '天', unit: 'd',
    options: [
      { v: '1d', label: '1天' }, { v: '3d', label: '3天' },
    ],
  },
  {
    label: '周', unit: 'w',
    options: [
      { v: '1w', label: '1周' },
    ],
  },
]

// 全部预置值, 用于判断当前值是否在预置中
const PRESETS = new Set(GROUPS.flatMap(g => g.options.map(o => o.v)))

// 自定义值
const showCustom = ref(false)
const customValue = ref('')
const customUnit = ref('m')
const customNum = ref(15)

watch(() => props.modelValue, (v) => {
  if (!v) return
  if (PRESETS.has(v)) {
    showCustom.value = false
  } else {
    // 解析自定义值
    const m = v.match(/^(\d+)([mhdw])$/)
    if (m) {
      showCustom.value = true
      customNum.value = +m[1]
      customUnit.value = m[2]
    } else {
      showCustom.value = true
      customValue.value = v
    }
  }
}, { immediate: true })

function select(tf) {
  showCustom.value = false
  emit('update:modelValue', tf)
  emit('change', tf)
}

function applyCustom() {
  const n = +customNum.value
  if (n < 1) return
  const tf = `${n}${customUnit.value}`
  emit('update:modelValue', tf)
  emit('change', tf)
}

function openCustom() {
  showCustom.value = true
}
</script>

<template>
  <div class="tf-picker">
    <span class="lbl">K线</span>
    <div v-for="g in GROUPS" :key="g.label" class="group">
      <span class="glbl">{{ g.label }}</span>
      <button v-for="o in g.options" :key="o.v"
        :class="{ active: modelValue === o.v && !showCustom }"
        @click="select(o.v)" :title="`${o.label} (${o.v})`">{{ o.label }}</button>
    </div>
    <div class="group custom-grp">
      <button class="custom-btn" :class="{ active: showCustom }"
        @click="openCustom" title="自定义周期">自定义</button>
      <div v-if="showCustom" class="custom-editor">
        <input type="number" v-model.number="customNum" min="1" max="999" />
        <select v-model="customUnit">
          <option value="m">分</option>
          <option value="h">时</option>
          <option value="d">天</option>
          <option value="w">周</option>
        </select>
        <button class="apply" @click="applyCustom">应用</button>
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
.custom-editor input, .custom-editor select {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 4px 6px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  width: 60px;
}
.custom-editor select { width: 50px; }
.custom-editor input:focus, .custom-editor select:focus { border-color: var(--yellow); outline: none; }
.custom-editor .apply {
  background: var(--yellow);
  color: #000;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
}
</style>
