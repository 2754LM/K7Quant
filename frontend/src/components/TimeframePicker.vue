<script setup>
defineProps({
  timeframes: Array,
  modelValue: String,
})
const emit = defineEmits(['update:modelValue', 'change'])

function select(tf) {
  emit('update:modelValue', tf)
  emit('change', tf)
}
</script>

<template>
  <div class="picker">
    <span class="lbl">K线</span>
    <button v-for="tf in timeframes" :key="tf"
      :class="{ active: modelValue === tf }"
      @click="select(tf)">{{ tf }}</button>
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
.picker .lbl { font-size: 11px; color: var(--text-secondary); padding: 0 4px; }
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
</style>