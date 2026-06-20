<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  timeframes: Array,
  modelValue: String,
})
const emit = defineEmits(['update:modelValue', 'change'])

const customInput = ref('')

watch(() => props.modelValue, (v) => {
  if (v && !props.timeframes?.includes(v)) {
    customInput.value = v
  }
}, { immediate: true })

function select(tf) {
  customInput.value = ''
  emit('update:modelValue', tf)
  emit('change', tf)
}

function onCustomInput() {
  const v = customInput.value.trim()
  if (v) {
    emit('update:modelValue', v)
    emit('change', v)
  }
}
</script>

<template>
  <div class="picker">
    <span class="lbl">K线</span>
    <button v-for="tf in timeframes" :key="tf"
      :class="{ active: modelValue === tf && !customInput }"
      @click="select(tf)">{{ tf }}</button>
    <input type="text" class="custom-input" v-model="customInput"
      placeholder="自定义" @change="onCustomInput" @blur="onCustomInput"
      :title="customInput || '输入自定义周期如 8h, 90m'" />
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  align-items: center;
  gap: 2px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 3px 6px;
}
.picker .lbl { font-size: 11px; color: var(--text-secondary); padding: 0 4px; white-space: nowrap; }
.picker button {
  background: transparent;
  color: var(--text-secondary);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-family: 'Consolas', monospace;
}
.picker button:hover { color: var(--text); }
.picker button.active {
  background: var(--yellow);
  color: #000;
  font-weight: 600;
}
.custom-input {
  background: transparent;
  border: 1px dashed var(--border);
  color: var(--text);
  padding: 3px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-family: 'Consolas', monospace;
  width: 60px;
  outline: none;
  margin-left: 4px;
}
.custom-input:focus { border-color: var(--yellow); border-style: solid; }
.custom-input::placeholder { color: var(--text-muted); font-size: 10px; }
</style>