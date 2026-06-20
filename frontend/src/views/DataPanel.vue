<script setup>
import { ref, onMounted, computed } from 'vue'
import { listData, clearDataCache, testConnection } from '../api'

import StateView from '../components/StateView.vue'

const data = ref({ files: [], total_size_kb: 0, by_timeframe: {} })
const conn = ref({})
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  try {
    const res = await listData()
    data.value = res.data
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function testConn() {
  try {
    const res = await testConnection()
    conn.value = res.data.binance
  } catch (e) {
    conn.value = { reachable: false, error: e.message }
  }
}

async function clear(timeframe, symbol) {
  if (!confirm(`确认删除 ${timeframe ? timeframe + ' ' : ''}${symbol || '全部'} 数据?`)) return
  await clearDataCache(timeframe, symbol)
  await load()
}

const grouped = computed(() => {
  const g = {}
  for (const f of data.value.files) {
    const [tf, name] = f.name.split('/')
    if (!g[tf]) g[tf] = []
    g[tf].push({ ...f, symbol: name.replace('.csv', '') })
  }
  return g
})

function formatTime(ts) { return new Date(ts * 1000).toLocaleString('zh-CN') }

onMounted(() => {
  load()
  testConn()
})
</script>

<template>
  <div class="data-panel">
    <div class="card">
      <div class="card-header">
        <h3>数据缓存</h3>
        <div class="actions">
          <button class="btn-secondary" @click="testConn">测试连接</button>
          <button class="btn-secondary" @click="load">刷新</button>
        </div>
      </div>

      <div class="conn-status" :class="{ ok: conn.reachable, err: conn.reachable === false }">
        <span class="status-dot"></span>
        <span v-if="conn.reachable === undefined">检测中...</span>
        <span v-else-if="conn.reachable">已连接 Binance ({{ conn.proxy_enabled ? `代理: ${conn.proxy?.https || conn.proxy?.http}` : '直连' }})</span>
        <span v-else>连接失败: {{ conn.error || '未知' }}</span>
      </div>

      <div class="info-row">
        <div class="stat"><span class="lbl">总文件数</span><span class="val">{{ data.files.length }}</span></div>
        <div class="stat"><span class="lbl">占用空间</span><span class="val">{{ (data.total_size_kb / 1024).toFixed(2) }} MB</span></div>
        <div class="stat"><span class="lbl">周期数</span><span class="val">{{ Object.keys(data.by_timeframe).length }}</span></div>
      </div>

      <div class="info-box">
        <p>📦 数据按 K 线周期分目录缓存：<code>data/{timeframe}/{symbol}.csv</code></p>
        <p>首次访问时自动从 Binance 下载, 后续直接读本地缓存</p>
      </div>

      <StateView :loading="loading && !data.files.length" :error="error" />
      <div v-for="(items, tf) in grouped" :key="tf" class="tf-group">
        <div class="tf-header">
          <h4>{{ tf }} 周期 ({{ items.length }})</h4>
          <button class="btn-danger" @click="clear(tf)">清空该周期</button>
        </div>
        <table>
          <thead><tr><th>文件名</th><th>大小</th><th>修改时间</th><th></th></tr></thead>
          <tbody>
            <tr v-for="f in items" :key="f.symbol">
              <td class="sym-cell">{{ f.symbol }}</td>
              <td>{{ f.size_kb }} KB</td>
              <td>{{ formatTime(f.mtime) }}</td>
              <td><button class="row-del" @click="clear(tf, f.symbol)">×</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!loading && !error && !data.files.length" class="empty-state">
        <div class="icon">📂</div>
        <div>暂无数据文件, 先在「智能回测」或「K线数据」页跑一次</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.data-panel { display: flex; flex-direction: column; gap: 16px; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.card-header h3 { font-size: 16px; }
.actions { display: flex; gap: 8px; }
.conn-status {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}
.conn-status.ok { border-color: rgba(2,192,118,0.3); }
.conn-status.err { border-color: rgba(246,70,93,0.3); color: var(--red); }
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
}
.conn-status.ok .status-dot { background: var(--green); }
.conn-status.err .status-dot { background: var(--red); }
.info-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.stat {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 12px;
  border-radius: 6px;
}
.stat .lbl { font-size: 12px; color: var(--text-secondary); }
.stat .val { font-size: 22px; font-weight: 700; color: var(--yellow); font-family: 'Consolas', monospace; margin-top: 4px; }
.info-box {
  background: rgba(30,136,229,0.08);
  border: 1px solid rgba(30,136,229,0.3);
  padding: 16px;
  border-radius: 6px;
  margin-bottom: 20px;
  font-size: 13px;
  line-height: 1.8;
  color: #64b5f6;
}
.info-box code {
  background: var(--bg-elevated);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', monospace;
  color: var(--yellow);
}
.tf-group { margin-bottom: 24px; }
.tf-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.tf-header h4 {
  font-size: 14px;
  color: var(--yellow);
  font-family: 'Consolas', monospace;
}
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left;
  padding: 10px;
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  border-bottom: 1px solid var(--border);
}
td {
  padding: 10px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
tr:hover td { background: var(--bg-elevated); }
.sym-cell { font-weight: 600; color: var(--yellow); }
.row-del { background: transparent; color: var(--red); font-size: 18px; padding: 2px 8px; border-radius: 4px; }
.row-del:hover { background: rgba(246,70,93,0.2); }
</style>