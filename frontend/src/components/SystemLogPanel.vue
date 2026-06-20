<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { NBadge, NButton, NEmpty, NScrollbar, NTag } from 'naive-ui'
import { getLogs, clear as clearLogs, subscribe } from '../utils/systemLog'

const logs = ref(getLogs())
const panelOpen = ref(false)

let unsub = null
onMounted(() => {
  unsub = subscribe((newLogs) => { logs.value = newLogs })
})
onUnmounted(() => { if (unsub) unsub() })

const errorCount = computed(() => logs.value.filter(l => l.level === 'error').length)
const warnCount = computed(() => logs.value.filter(l => l.level === 'warn').length)

const LEVEL_ICON = { info: 'ℹ️', success: '✓', warn: '⚠️', error: '✗' }
const LEVEL_COLOR = { info: '#b7bdc6', success: '#02c076', warn: '#f0b90b', error: '#f6465d' }

function toggle() { panelOpen.value = !panelOpen.value }
function close() { panelOpen.value = false }
function clearAll() { clearLogs() }

function fmtTime(d) {
  const dt = new Date(d)
  return dt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>

<template>
  <div class="log-bell-wrap" v-click-outside="close">
    <n-badge :value="errorCount || null" :max="99" :show="errorCount > 0" type="error">
      <button class="log-bell" :class="{ active: panelOpen, hasWarn: warnCount > 0, hasError: errorCount > 0 }"
        @click="toggle" :title="errorCount ? `${errorCount} 个错误` : '系统日志'">
        🔔
        <span v-if="warnCount && !errorCount" class="warn-dot"></span>
      </button>
    </n-badge>

    <transition name="dropdown">
      <div v-if="panelOpen" class="log-panel">
        <div class="log-head">
          <span class="title">📋 系统日志</span>
          <div class="head-actions">
            <n-tag :bordered="false" size="small" type="error" v-if="errorCount">{{ errorCount }} 错误</n-tag>
            <n-tag :bordered="false" size="small" type="warning" v-if="warnCount">{{ warnCount }} 警告</n-tag>
            <n-button text size="tiny" @click="clearAll" :disabled="!logs.length">清空</n-button>
          </div>
        </div>
        <n-scrollbar style="max-height: 480px">
          <div v-if="!logs.length" class="empty">
            <n-empty description="暂无日志" />
          </div>
          <div v-else class="log-list">
            <div v-for="log in logs" :key="log.id" class="log-item" :class="log.level">
              <span class="log-icon" :style="{ color: LEVEL_COLOR[log.level] }">{{ LEVEL_ICON[log.level] }}</span>
              <span class="log-time">{{ fmtTime(log.ts) }}</span>
              <n-tag :bordered="false" size="small" :color="{ color: 'rgba(255,255,255,0.05)' }">{{ log.source }}</n-tag>
              <span class="log-msg">{{ log.message }}</span>
            </div>
          </div>
        </n-scrollbar>
      </div>
    </transition>
  </div>
</template>

<script>
// click-outside 指令
import { onMounted as onMounted2, onUnmounted as onUnmounted2 } from 'vue'
const handlers = new Map()
function bindOutside(el, handler) {
  const fn = (e) => { if (!el.contains(e.target)) handler() }
  document.addEventListener('mousedown', fn)
  handlers.set(handler, { el, fn })
}
function unbindOutside(handler) {
  const h = handlers.get(handler)
  if (h) { document.removeEventListener('mousedown', h.fn); handlers.delete(handler) }
}
export const vClickOutside = {
  mounted(el, binding) { bindOutside(el, binding.value) },
  unmounted(el, binding) { unbindOutside(binding.value) },
}
</script>

<style scoped>
.log-bell-wrap { position: relative; display: inline-flex; align-items: center; }
.log-bell {
  background: transparent;
  font-size: 18px;
  padding: 6px 8px;
  border-radius: 6px;
  position: relative;
  transition: background 0.15s;
}
.log-bell:hover { background: var(--bg-elevated); }
.log-bell.active { background: var(--bg-elevated); }
.log-bell.hasError { animation: shake 0.4s ease; }
.log-bell .warn-dot {
  position: absolute; top: 4px; right: 4px;
  width: 8px; height: 8px;
  background: var(--yellow);
  border-radius: 50%;
}
@keyframes shake { 0%, 100% { transform: rotate(0); } 25% { transform: rotate(-8deg); } 75% { transform: rotate(8deg); } }

.log-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 480px;
  max-width: 90vw;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  z-index: 200;
  overflow: hidden;
}
.log-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}
.log-head .title { font-size: 14px; font-weight: 600; color: var(--text); }
.head-actions { display: flex; align-items: center; gap: 8px; }
.log-list { padding: 6px 0; }
.log-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.log-item:hover { background: var(--bg-elevated); }
.log-item.error { border-left: 3px solid var(--red); }
.log-item.warn { border-left: 3px solid var(--yellow); }
.log-item.success { border-left: 3px solid var(--green); }
.log-icon { flex-shrink: 0; font-size: 12px; }
.log-time { color: var(--text-muted); flex-shrink: 0; font-size: 11px; }
.log-msg { color: var(--text); flex: 1; word-break: break-all; }
.empty { padding: 40px 0; }
.dropdown-enter-active, .dropdown-leave-active { transition: opacity 0.15s, transform 0.15s; }
.dropdown-enter-from, .dropdown-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
