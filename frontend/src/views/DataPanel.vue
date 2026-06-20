<script setup>
import { ref, onMounted } from 'vue'
import { listData } from '../api'

const files = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await listData()
    files.value = res.data.files
  } finally {
    loading.value = false
  }
}

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

const grouped = ref({})
function groupByTf() {
  const g = {}
  for (const f of files.value) {
    const parts = f.name.split('/')
    const tf = parts.length > 1 ? parts[0] : 'root'
    if (!g[tf]) g[tf] = []
    g[tf].push(f)
  }
  grouped.value = g
}

onMounted(async () => {
  await load()
  groupByTf()
})
</script>

<template>
  <div class="data-panel">
    <div class="panel-header">
      <h3>数据缓存管理</h3>
      <button @click="async () => { await load(); groupByTf() }" :disabled="loading">
        {{ loading ? '加载中' : '刷新' }}
      </button>
    </div>

    <div class="info-box">
      <p>📦 数据按 K线周期分目录缓存：<code>data/4h/BTCUSDT.csv</code></p>
      <p>首次访问时自动从 Binance 下载，后续直接读本地缓存</p>
    </div>

    <div v-for="(items, tf) in grouped" :key="tf" class="tf-group">
      <h4>{{ tf === 'root' ? '根目录' : tf + ' 周期' }} ({{ items.length }})</h4>
      <table>
        <thead><tr><th>文件名</th><th>大小</th><th>修改时间</th></tr></thead>
        <tbody>
          <tr v-for="f in items" :key="f.name">
            <td>{{ f.name }}</td>
            <td>{{ f.size_kb }} KB</td>
            <td>{{ formatTime(f.mtime) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="!files.length" class="empty">暂无数据文件，先在回测或 K线页跑一次</div>
  </div>
</template>

<style scoped>
.data-panel {
  background: var(--binance-card);
  border: 1px solid var(--binance-border);
  border-radius: 12px;
  padding: 24px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.panel-header h3 { font-size: 18px; }
.panel-header button {
  background: var(--binance-yellow);
  color: #0b0e11;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
}
.info-box {
  background: #1e88e511;
  border: 1px solid #1e88e544;
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 20px;
  font-size: 13px;
  line-height: 1.8;
}
.info-box code {
  background: #0b0e11;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', monospace;
  color: var(--binance-yellow);
}
.tf-group {
  margin-bottom: 24px;
}
.tf-group h4 {
  font-size: 14px;
  color: var(--binance-yellow);
  margin-bottom: 8px;
  font-family: 'Consolas', monospace;
}
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left;
  padding: 10px;
  background: #0b0e11;
  color: var(--binance-text-secondary);
  font-size: 12px;
  font-weight: 500;
  border-bottom: 1px solid var(--binance-border);
}
td {
  padding: 10px;
  border-bottom: 1px solid #2b3139;
  font-size: 14px;
  font-family: 'Consolas', monospace;
}
tr:hover td { background: #181a20; }
.empty {
  text-align: center;
  padding: 60px;
  color: var(--binance-text-secondary);
}
</style>