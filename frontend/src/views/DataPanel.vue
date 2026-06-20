<script setup>
import { ref, onMounted, computed } from 'vue'
import { listData, clearData } from '../api'

const data = ref({ files: [], total_size_kb: 0, by_timeframe: {} })
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await listData()
    data.value = res.data
  } finally {
    loading.value = false
  }
}

async function clear(timeframe, symbol) {
  if (!confirm(`确认删除 ${timeframe ? timeframe + ' ' : ''}${symbol || '全部'} 数据？`)) return
  await clearData(timeframe, symbol)
  await load()
}

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleString('zh-CN')
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

onMounted(load)
</script>

<template>
  <div class="data-panel">
    <div class="panel-header">
      <h3>数据缓存管理</h3>
      <button @click="load" :disabled="loading">{{ loading ? '加载中' : '刷新' }}</button>
    </div>

    <div class="info-row">
      <div class="stat-card">
        <div class="lbl">总文件数</div>
        <div class="val">{{ data.files.length }}</div>
      </div>
      <div class="stat-card">
        <div class="lbl">占用空间</div>
        <div class="val">{{ (data.total_size_kb / 1024).toFixed(2) }} MB</div>
      </div>
      <div class="stat-card">
        <div class="lbl">周期数</div>
        <div class="val">{{ Object.keys(data.by_timeframe).length }}</div>
      </div>
    </div>

    <div class="info-box">
      <p>📦 数据按 K 线周期分目录缓存：<code>data/4h/BTCUSDT.csv</code></p>
      <p>首次访问时自动从 Binance 下载，后续直接读本地缓存</p>
    </div>

    <div v-for="(items, tf) in grouped" :key="tf" class="tf-group">
      <div class="tf-header">
        <h4>{{ tf }} 周期 ({{ items.length }} 个币种)</h4>
        <button class="del-btn" @click="clear(tf)">清空该周期</button>
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

    <div v-if="!data.files.length" class="empty">暂无数据文件，先在「智能回测」或「K线数据」页跑一次</div>
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
.info-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.stat-card {
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  padding: 14px;
  border-radius: 8px;
}
.stat-card .lbl { font-size: 12px; color: var(--binance-text-secondary); margin-bottom: 6px; }
.stat-card .val { font-size: 22px; font-weight: 700; color: var(--binance-yellow); font-family: 'Consolas', monospace; }
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
.tf-group { margin-bottom: 24px; }
.tf-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.tf-header h4 {
  font-size: 14px;
  color: var(--binance-yellow);
  font-family: 'Consolas', monospace;
}
.del-btn {
  background: transparent;
  color: #f6465d;
  border: 1px solid #f6465d;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 11px;
}
.del-btn:hover { background: #f6465d22; }
.row-del {
  background: transparent;
  color: #f6465d;
  font-size: 18px;
  padding: 2px 8px;
  border-radius: 4px;
}
.row-del:hover { background: #f6465d22; }
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left;
  padding: 10px;
  background: #0b0e11;
  color: var(--binance-text-secondary);
  font-size: 11px;
  font-weight: 500;
  border-bottom: 1px solid var(--binance-border);
}
td {
  padding: 10px;
  border-bottom: 1px solid #2b3139;
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
tr:hover td { background: #181a20; }
.sym-cell { font-weight: 600; color: var(--binance-yellow); }
.empty {
  text-align: center;
  padding: 60px;
  color: var(--binance-text-secondary);
}
</style>