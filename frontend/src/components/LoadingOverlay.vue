<script setup>
defineProps({
  loading: Boolean,
  text: { type: String, default: '加载中...' },
  inline: Boolean,  // 是否使用 inline 模式 (覆盖整个父容器)
})
</script>

<template>
  <transition name="fade">
    <div v-if="loading" class="loading-overlay" :class="{ inline }">
      <div class="spinner"></div>
      <span class="text">{{ text }}</span>
    </div>
  </transition>
</template>

<style scoped>
.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(24, 26, 32, 0.7);
  backdrop-filter: blur(2px);
  z-index: 50;
  border-radius: 12px;
  pointer-events: none;
}
.loading-overlay.inline {
  position: relative;
  inset: auto;
  min-height: 200px;
  background: transparent;
  backdrop-filter: none;
}
.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--border);
  border-top-color: var(--yellow);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.text {
  font-size: 13px;
  color: var(--text-secondary);
}
@keyframes spin { to { transform: rotate(360deg); } }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
