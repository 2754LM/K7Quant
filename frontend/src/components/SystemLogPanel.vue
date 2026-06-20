<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { NBadge, NButton, NScrollbar, NTag } from 'naive-ui'
import { getLogs, subscribe } from '../utils/systemLog'

const logs = ref(getLogs())
const panelOpen = ref(false)

let unsub = null
onMounted(() => {
  unsub = subscribe((newLogs) => { logs.value = newLogs })
})
onUnmounted(() => { if (unsub) unsub() })

const errorCount = computed(() => logs.value.filter(l => l.level === 'error').length)
const warnCount = computed(() => logs.value.filter(l => l.level === 'warn').length)
const recentErrors = computed(() =>
  logs.value.filter(l => l.level === 'error' || l.level === 'warn').slice(0, 5)
)

const LEVEL_ICON = { info: 'ℹ️', success: '✓', warn: '⚠️', error: '✗' }
const LEVEL_COLOR = { info: '#b7bdc6', success: '#02c076', warn: '#f0b90b', error: '#f6465d' }

function toggle() { panelOpen.value = !panelOpen.value }
function close() { panelOpen.value = false }
function gotoFull() {
  window.location.hash = '#log'
  // 触发 App.vue 的 hashchange (也可以用 router.push, 但这里没有 router)
  const evt = new CustomEvent('navigate', { detail: 'logs' })
  window.dispatchEvent(evt)
  close()
}

function fmtTime(d) {
  const dt = new Date(d)
  return dt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

let outsideHandler = null
onMounted(() => {
  outsideHandler = (e) => {
    const wrap = document.querySelector('.log-bell-wrap')
    if (wrap && !wrap.contains(e.target)) close()
  }
  document.addEventListener('mousedown', outsideHandler)
})
onUnmounted(() => {
  if (unsub) unsub()
  if (outsideHandler) document.removeEventListener('mousedown', outsideHandler)
})
</script>

<template>
  <div class="log-bell-wrap">
    <n-badge :value="errorCount || null" :max="99" :show="errorCount > 0" type="error">
      <button class="log-bell" :class="{ active: panelOpen, hasError: errorCount > 0, hasWarn: warnCount > 0 && !errorCount }"
        @click="toggle" :title="errorCount ? `${errorCount} 个错误` : (warnCount ? `${warnCount} 个警告` : '系统日志')">
        🔔
      </button>
    </n-badge>

    <transition name="dropdown">
      <div v-if="panelOpen" class="notify-panel">
        <div class="panel-head">
          <span class="title">🔔 关键提示</span>
          <span class="head-actions">
            <n-tag :bordered="false" size="small" type="error" v-if="errorCount">{{ errorCount }} 错误</n-tag>
            <n-tag :bordered="false" size="small" type="warning" v-if="warnCount">{{ warnCount }} 警告</n-tag>
          </span>
        </div>
        <n-scrollbar style="max-height: 320px">
          <div v-if="!recentErrors.length" class="empty-state">
            <span class="check">✓</span>
            <span>运行正常, 暂无错误或警告</span>
          </div>
          <div v-else class="notify-list">
            <div v-for="log in recentErrors" :key="log.id" class="notify-item" :class="log.level">
              <span class="notify-icon" :style="{ color: LEVEL_COLOR[log.level] }">
                {{ LEVEL_ICON[log.level] }}
              </span>
              <div class="notify-body">
                <div class="notify-msg">{{ log.message }}</div>
                <div class="notify-meta">
                  <span class="source">{{ log.source }}</span>
                  <span class="time">{{ fmtTime(log.ts) }}</span>
                </div>
              </div>
            </div>
          </div>
        </n-scrollbar>
        <div class="panel-foot">
          <n-button size="tiny" block @click="gotoFull">查看完整日志 →</n-button>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.log-bell-wrap { position: relative; display: inline-flex; align-items: center; }
.log-bell {
  background: transparent;
  font-size: 18px;
  padding: 6px 8px;
  border-radius: 6px;
  transition: background 0.15s, transform 0.2s;
}
.log-bell:hover { background: var(--bg-elevated); }
.log-bell.active { background: var(--bg-elevated); }
.log-bell.hasError { animation: shake 0.4s ease; }
.log-bell.hasWarn { background: rgba(240,185,11,0.1); }
@keyframes shake {
  0%, 100% { transform: rotate(0); }
  25% { transform: rotate(-8deg); }
  75% { transform: rotate(8deg); }
}

.notify-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 360px;
  max-width: 90vw;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  z-index: 200;
  overflow: hidden;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  font-size: 13px;
}
.panel-head .title { font-weight: 600; color: var(--text); }
.head-actions { display: flex; gap: 6px; }
.notify-list { padding: 6px 0; }
.notify-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.notify-item:hover { background: var(--bg-elevated); }
.notify-item.error { border-left: 3px solid var(--red); }
.notify-item.warn { border-left: 3px solid var(--yellow); }
.notify-icon { flex-shrink: 0; font-size: 14px; margin-top: 1px; }
.notify-body { flex: 1; min-width: 0; }
.notify-msg {
  color: var(--text);
  font-size: 12px;
  line-height: 1.5;
  word-break: break-all;
}
.notify-meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  font-size: 10px;
  color: var(--text-muted);
  font-family: 'Consolas', monospace;
}
.notify-meta .source {
  background: var(--bg);
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 16px;
  color: var(--green);
  font-size: 13px;
}
.empty-state .check {
  font-size: 36px;
  color: var(--green);
}
.panel-foot {
  border-top: 1px solid var(--border);
  padding: 8px 14px;
  background: var(--bg);
}
.dropdown-enter-active, .dropdown-leave-active { transition: opacity 0.15s, transform 0.15s; }
.dropdown-enter-from, .dropdown-leave-to { opacity: 0; transform: translateY(-8px); }
</style>