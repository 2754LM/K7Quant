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
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  border-radius: 8px;
  padding: 3px;
}
.picker button {
  background: transparent;
  color: var(--binance-text-secondary);
  padding: 5px 9px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  transition: all 0.2s;
}
.picker button:hover { color: var(--binance-text); }
.picker button.active {
  background: var(--binance-yellow);
  color: #0b0e11;
  font-weight: 600;
}
</style>