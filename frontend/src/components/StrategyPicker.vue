<script setup>
defineProps({
  strategies: Array,
  modelValue: String,
})

const emit = defineEmits(['update:modelValue', 'change'])

function select(id) {
  emit('update:modelValue', id)
  emit('change', id)
}
</script>

<template>
  <div class="picker">
    <button v-for="s in strategies" :key="s.id"
      :class="{ active: modelValue === s.id }"
      @click="select(s.id)"
      :title="s.description">
      <span class="icon">{{ s.icon }}</span>
      <span class="name">{{ s.name }}</span>
    </button>
  </div>
</template>

<style scoped>
.picker { display: flex; gap: 6px; flex-wrap: wrap; }
.picker button {
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  color: var(--binance-text-secondary);
  padding: 8px 14px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
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
.icon { font-size: 16px; }
</style>