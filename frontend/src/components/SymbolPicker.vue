<script setup>
import { computed } from 'vue'

const props = defineProps({
  symbols: Array,
  info: Object,
  modelValue: [String, Array],
  multiple: Boolean,
  showInfo: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue', 'change'])

function infoOf(sym) {
  return props.info?.[sym] || {}
}

function isSelected(sym) {
  if (props.multiple) {
    return (props.modelValue || []).includes(sym)
  }
  return props.modelValue === sym
}

function toggle(sym) {
  if (props.multiple) {
    const arr = [...(props.modelValue || [])]
    const i = arr.indexOf(sym)
    if (i >= 0) arr.splice(i, 1)
    else arr.push(sym)
    emit('update:modelValue', arr)
    emit('change', arr)
  } else {
    emit('update:modelValue', sym)
    emit('change', sym)
  }
}
</script>

<template>
  <div class="picker">
    <button v-for="sym in symbols" :key="sym"
      :class="{ active: isSelected(sym) }"
      @click="toggle(sym)">
      <span class="sym">{{ sym }}</span>
      <span v-if="showInfo && infoOf(sym).name_zh" class="name">{{ infoOf(sym).name_zh }}</span>
    </button>
  </div>
</template>

<style scoped>
.picker { display: flex; gap: 4px; flex-wrap: wrap; }
.picker button {
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  color: var(--binance-text-secondary);
  padding: 6px 10px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  transition: all 0.2s;
}
.picker button:hover {
  border-color: var(--binance-yellow);
  color: var(--binance-text);
}
.picker button.active {
  background: #f0b90b11;
  border-color: var(--binance-yellow);
  color: var(--binance-yellow);
}
.sym { font-family: 'Consolas', monospace; font-weight: 600; }
.name { font-size: 11px; opacity: 0.8; }
</style>