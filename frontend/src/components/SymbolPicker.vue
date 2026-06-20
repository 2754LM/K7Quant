<script setup>
defineProps({
  label: String,
  modelValue: [String, Array],
  options: Array,
  multiple: Boolean,
  info: Object,
  showInfo: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue', 'change'])

function infoOf(opt) {
  if (typeof opt === 'string') {
    return props.info?.[opt] || {}
  }
  return opt
}

import { computed } from 'vue'
const props = defineProps({})

function isSelected(opt) {
  const key = typeof opt === 'string' ? opt : opt.value
  if (props.multiple) {
    return (props.modelValue || []).includes(key)
  }
  return props.modelValue === key
}

function toggle(opt) {
  const key = typeof opt === 'string' ? opt : opt.value
  if (props.multiple) {
    const arr = [...(props.modelValue || [])]
    const i = arr.indexOf(key)
    if (i >= 0) arr.splice(i, 1)
    else arr.push(key)
    emit('update:modelValue', arr)
    emit('change', arr)
  } else {
    emit('update:modelValue', key)
    emit('change', key)
  }
}
</script>

<template>
  <div class="picker">
    <button v-for="opt in options" :key="typeof opt === 'string' ? opt : opt.value"
      :class="{ active: isSelected(opt) }"
      @click="toggle(opt)">
      <span class="code">{{ typeof opt === 'string' ? opt : opt.value }}</span>
      <span v-if="showInfo && infoOf(opt).name_zh" class="name">{{ infoOf(opt).name_zh }}</span>
    </button>
  </div>
</template>

<style scoped>
.picker { display: flex; gap: 4px; flex-wrap: wrap; }
.picker button {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 6px 10px;
  border-radius: 6px;
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
.code { font-family: 'Consolas', monospace; font-weight: 600; }
.name { font-size: 11px; opacity: 0.8; }
</style>