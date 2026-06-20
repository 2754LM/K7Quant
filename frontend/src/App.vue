<script setup>
import { ref, onMounted } from 'vue'
import Dashboard from './views/Dashboard.vue'
import KLine from './views/KLine.vue'
import Filter from './views/Filter.vue'
import Learn from './views/Learn.vue'
import DataPanel from './views/DataPanel.vue'
import { getConfig } from './api'

const activeTab = ref('dashboard')
const cfg = ref(null)

onMounted(async () => {
  try {
    const res = await getConfig()
    cfg.value = res.data
  } catch (e) {
    console.error(e)
  }
})
</script>

<template>
  <div class="layout">
    <header class="header">
      <div class="logo">
        <span class="logo-icon">⚡</span>
        <div class="logo-text">
          <div class="title">K7Quant</div>
          <div class="subtitle">币安量化回测系统</div>
        </div>
      </div>
      <nav class="nav">
        <button :class="{ active: activeTab === 'dashboard' }" @click="activeTab = 'dashboard'">
          智能回测
        </button>
        <button :class="{ active: activeTab === 'kline' }" @click="activeTab = 'kline'">
          K 线数据
        </button>
        <button :class="{ active: activeTab === 'filter' }" @click="activeTab = 'filter'">
          币种筛选
        </button>
        <button :class="{ active: activeTab === 'data' }" @click="activeTab = 'data'">
          数据缓存
        </button>
        <button :class="{ active: activeTab === 'learn' }" @click="activeTab = 'learn'">
          量化课堂
        </button>
      </nav>
      <div class="status" v-if="cfg">
        <span class="badge yellow">{{ cfg.symbols.length }} 币种</span>
        <span class="badge">{{ cfg.timeframes.length }} 周期</span>
      </div>
    </header>

    <main class="main">
      <Dashboard v-if="activeTab === 'dashboard' && cfg" :cfg="cfg" />
      <KLine v-else-if="activeTab === 'kline' && cfg" :cfg="cfg" />
      <Filter v-else-if="activeTab === 'filter' && cfg" :cfg="cfg" />
      <DataPanel v-else-if="activeTab === 'data'" />
      <Learn v-else-if="activeTab === 'learn'" :cfg="cfg" />
      <div v-else class="loading">加载中...</div>
    </main>
  </div>
</template>

<style scoped>
.layout { min-height: 100vh; display: flex; flex-direction: column; }
.header {
  background: #181a20;
  border-bottom: 1px solid #2b3139;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 32px;
  position: sticky;
  top: 0;
  z-index: 10;
}
.logo { display: flex; align-items: center; gap: 12px; }
.logo-icon { font-size: 28px; color: var(--binance-yellow); }
.logo-text .title { font-size: 18px; font-weight: 700; color: var(--binance-yellow); letter-spacing: 1px; }
.logo-text .subtitle { font-size: 11px; color: var(--binance-text-secondary); }
.nav { display: flex; gap: 4px; flex: 1; }
.nav button {
  background: transparent;
  color: var(--binance-text-secondary);
  padding: 8px 18px;
  border-radius: 6px;
  font-size: 13px;
  transition: all 0.2s;
}
.nav button:hover { color: var(--binance-text); background: #2b3139; }
.nav button.active { color: var(--binance-yellow); background: #2b3139; }
.status { display: flex; gap: 8px; }
.badge {
  background: #2b3139;
  color: var(--binance-text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
}
.badge.yellow { background: #f0b90b22; color: var(--binance-yellow); border: 1px solid #f0b90b44; }
.main {
  flex: 1;
  padding: 24px;
  max-width: 1600px;
  margin: 0 auto;
  width: 100%;
}
.loading {
  text-align: center;
  padding: 100px 0;
  color: var(--binance-text-secondary);
}
</style>