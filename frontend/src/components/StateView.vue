<script setup>
defineProps({
  loading: Boolean,
  empty: Boolean,
  error: String,
  emptyText: { type: String, default: '暂无数据' },
  emptyIcon: { type: String, default: '📭' },
})
</script>

<template>
  <div v-if="loading" class="loading">
    <div class="spinner"></div>
    <span>加载中...</span>
  </div>
  <div v-else-if="error" class="error">
    <div class="icon">⚠️</div>
    <div>{{ error }}</div>
  </div>
  <div v-else-if="empty" class="empty-state">
    <div class="icon">{{ emptyIcon }}</div>
    <div>{{ emptyText }}</div>
  </div>
  <slot v-else />
</template>

<style scoped>
.loading, .error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--text-secondary);
  gap: 12px;
}
.error { color: var(--red); }
.error .icon { font-size: 36px; }
</style>