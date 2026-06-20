<script setup>
defineProps({
  strategies: Array,
  modelValue: [String, Number],
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
      :class="{ active: Number(modelValue) === s.id }"
      @click="select(s.id)"
      :title="s.description">
      <span class="icon">{{ s.icon || '📊' }}</span>
      <span class="name">{{ s.name }}</span>
    </button>
  </div>
</template>

<style scoped>
.picker { display: flex; gap: 6px; flex-wrap: wrap; }
.picker button {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 8px 14px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
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
.icon { font-size: 16px; }
</style>