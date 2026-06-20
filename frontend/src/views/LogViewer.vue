<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import {
  NSelect, NInput, NButton, NEmpty, NScrollbar, NTooltip, NSwitch, NTag,
} from 'naive-ui'
import { getLogs, clear as clearLogs, subscribe, info as logInfo } from '../utils/systemLog'

const logs = ref(getLogs())
const filterLevel = ref('all')      // all | error | warn | info | success
const filterSource = ref(null)      // null = all, or specific source string
const filterText = ref('')
const autoScroll = ref(true)
const showTimestamp = ref(true)

let unsub = null
const scrollRef = ref(null)

onMounted(() => {
  unsub = subscribe((newLogs) => {
    logs.value = newLogs
    if (autoScroll.value && scrollRef.value) {
      nextTick(() => {
        try { scrollRef.value.scrollTo({ top: 0, behavior: 'smooth' }) } catch (e) {}
      })
    }
  })
  logInfo('system', '系统日志页面已打开')
})
onUnmounted(() => { if (unsub) unsub() })

const LEVEL_ICON = { info: 'ℹ️', success: '✓', warn: '⚠️', error: '✗' }
const LEVEL_COLOR = { info: '#b7bdc6', success: '#02c076', warn: '#f0b90b', error: '#f6465d' }
const LEVEL_OPTS = [
  { label: '全部', value: 'all' },
  { label: '✗ 错误', value: 'error' },
  { label: '⚠️ 警告', value: 'warn' },
  { label: '✓ 成功', value: 'success' },
  { label: 'ℹ️ 信息', value: 'info' },
]

// 全部 source (从现有日志动态生成)
const sourceOpts = computed(() => {
  const set = new Set()
  for (const l of logs.value) if (l.source) set.add(l.source)
  return [{ label: '全部来源', value: null }, ...Array.from(set).sort().map(s => ({ label: s, value: s }))]
})

const filtered = computed(() => {
  let arr = logs.value
  if (filterLevel.value !== 'all') arr = arr.filter(l => l.level === filterLevel.value)
  if (filterSource.value) arr = arr.filter(l => l.source === filterSource.value)
  if (filterText.value.trim()) {
    const t = filterText.value.trim().toLowerCase()
    arr = arr.filter(l => (l.message || '').toLowerCase().includes(t))
  }
  return arr
})

const stats = computed(() => {
  const r = { total: logs.value.length, error: 0, warn: 0, info: 0, success: 0 }
  for (const l of logs.value) {
    if (r[l.level] !== undefined) r[l.level]++
  }
  return r
})

function fmtTime(d) {
  const dt = new Date(d)
  const pad = n => String(n).padStart(2, '0')
  return `${pad(dt.getHours())}:${pad(dt.getMinutes())}:${pad(dt.getSeconds())}.${String(dt.getMilliseconds()).padStart(3, '0')}`
}
function fmtDate(d) {
  const dt = new Date(d)
  const pad = n => String(n).padStart(2, '0')
  return `${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())}`
}
function clearAll() {
  if (confirm('确认清空所有日志? 该操作不可撤销。')) clearLogs()
}
async function copyAll() {
  const text = filtered.value.map(l =>
    `[${fmtDate(l.ts)} ${fmtTime(l.ts)}] [${l.level.toUpperCase()}] [${l.source}] ${l.message}`
  ).join('\n')
  try {
    await navigator.clipboard.writeText(text)
    logInfo('system', `已复制 ${filtered.value.length} 条日志到剪贴板`)
  } catch (e) {
    logInfo('system', '复制失败: 浏览器不支持剪贴板')
  }
}
function downloadLog() {
  const text = filtered.value.map(l =>
    `[${fmtDate(l.ts)} ${fmtTime(l.ts)}] [${l.level.toUpperCase()}] [${l.source}] ${l.message}`
  ).join('\n')
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `k7quant-logs-${fmtDate(new Date()).replace(/-/g, '')}-${fmtTime(new Date()).replace(/[:.]/g, '')}.txt`
  a.click()
  URL.revokeObjectURL(url)
  logInfo('system', '日志已导出')
}

function rowClass(level) {
  if (level === 'error') return 'row-error'
  if (level === 'warn') return 'row-warn'
  return ''
}
</script>

<template>
  <div class="log-viewer">
    <div class="header">
      <div class="title-area">
        <h2>📋 系统日志</h2>
        <span class="subtitle">所有 API 调用、错误、警告, 按时间倒序</span>
      </div>
      <div class="stats">
        <span class="stat" :class="{ active: filterLevel === 'all' }" @click="filterLevel = 'all'">
          总 <strong>{{ stats.total }}</strong>
        </span>
        <span class="stat err" :class="{ active: filterLevel === 'error' }" @click="filterLevel = 'error'">
          ✗ <strong>{{ stats.error }}</strong>
        </span>
        <span class="stat warn" :class="{ active: filterLevel === 'warn' }" @click="filterLevel = 'warn'">
          ⚠ <strong>{{ stats.warn }}</strong>
        </span>
        <span class="stat ok" :class="{ active: filterLevel === 'success' }" @click="filterLevel = 'success'">
          ✓ <strong>{{ stats.success }}</strong>
        </span>
        <span class="stat info" :class="{ active: filterLevel === 'info' }" @click="filterLevel = 'info'">
          ℹ <strong>{{ stats.info }}</strong>
        </span>
      </div>
    </div>

    <div class="toolbar">
      <n-select v-model:value="filterLevel" :options="LEVEL_OPTS" size="small" style="width: 130px" />
      <n-select v-model:value="filterSource" :options="sourceOpts" size="small" style="width: 160px" placeholder="来源" />
      <n-input v-model:value="filterText" size="small" placeholder="🔍 搜索消息内容..." style="flex:1;min-width:180px" clearable />
      <n-tooltip placement="top">
        <template #trigger>
          <n-switch v-model:value="autoScroll" size="small">
            <template #checked>新日志自动滚动</template>
            <template #unchecked>不滚动</template>
          </n-switch>
        </template>
        开启后, 新日志进来自动滚到顶部
      </n-tooltip>
      <n-tooltip placement="top">
        <template #trigger>
          <n-switch v-model:value="showTimestamp" size="small">
            <template #checked>显示时间</template>
            <template #unchecked>隐藏时间</template>
          </n-switch>
        </template>
        是否在每行显示毫秒级时间戳
      </n-tooltip>
      <n-button size="small" @click="copyAll" :disabled="!filtered.length">📋 复制</n-button>
      <n-button size="small" @click="downloadLog" :disabled="!filtered.length">💾 导出</n-button>
      <n-button size="small" type="warning" @click="clearAll" :disabled="!logs.length">🗑 清空</n-button>
    </div>

    <div class="log-container">
      <n-scrollbar ref="scrollRef" style="max-height: calc(100vh - 280px)">
        <div v-if="!filtered.length" class="empty">
          <n-empty :description="logs.length ? '没有符合条件的日志' : '暂无日志'" />
        </div>
        <div v-else class="log-list">
          <div v-for="log in filtered" :key="log.id"
            :class="['log-row', rowClass(log.level), log.level]">
            <span v-if="showTimestamp" class="log-time" :title="fmtDate(log.ts)">
              {{ fmtTime(log.ts) }}
            </span>
            <span class="log-icon" :style="{ color: LEVEL_COLOR[log.level] }">
              {{ LEVEL_ICON[log.level] }}
            </span>
            <span class="log-source" :data-level="log.level">{{ log.source }}</span>
            <span class="log-msg">{{ log.message }}</span>
          </div>
        </div>
      </n-scrollbar>
    </div>

    <div class="footer">
      <span class="hint">显示 {{ filtered.length }} / {{ logs.length }} 条</span>
      <span class="hint">仅在浏览器内存, 最多保留 200 条</span>
    </div>
  </div>
</template>

<style scoped>
.log-viewer {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 12px;
}
.title-area h2 {
  font-size: 22px;
  color: var(--yellow);
  margin: 0 0 4px;
}
.subtitle {
  font-size: 12px;
  color: var(--text-secondary);
}
.stats {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.stat {
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  font-family: 'Consolas', monospace;
}
.stat strong { color: var(--text); margin-left: 4px; }
.stat:hover { border-color: var(--yellow); }
.stat.active {
  background: var(--yellow);
  border-color: var(--yellow);
  color: #000;
  font-weight: 600;
}
.stat.active strong { color: #000; }
.stat.err { border-left: 3px solid var(--red); }
.stat.warn { border-left: 3px solid var(--yellow); }
.stat.ok { border-left: 3px solid var(--green); }
.stat.info { border-left: 3px solid #3498db; }

.toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  flex-wrap: wrap;
}
.log-container {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 0;
}
.log-list { padding: 0; }
.log-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  font-family: 'Consolas', monospace;
  font-size: 12px;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.log-row:hover { background: var(--bg-elevated); }
.log-row.error { border-left: 3px solid var(--red); background: rgba(246,70,93,0.04); }
.log-row.warn { border-left: 3px solid var(--yellow); }
.log-row.success { border-left: 3px solid var(--green); }
.log-time {
  color: var(--text-muted);
  font-size: 11px;
  flex-shrink: 0;
  width: 80px;
}
.log-icon { flex-shrink: 0; font-size: 12px; width: 16px; }
.log-source {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 10px;
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  min-width: 70px;
  text-align: center;
}
.log-source[data-level="error"] { color: var(--red); border-color: var(--red); }
.log-source[data-level="warn"] { color: var(--yellow); border-color: var(--yellow); }
.log-source[data-level="success"] { color: var(--green); border-color: var(--green); }
.log-source[data-level="info"] { color: #3498db; border-color: #3498db; }
.log-msg {
  color: var(--text);
  flex: 1;
  word-break: break-all;
}
.empty { padding: 80px 0; }

.footer {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-muted);
  padding: 0 4px;
}
.hint { color: var(--text-muted); }
</style>