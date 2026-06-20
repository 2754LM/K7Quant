<script setup>
import { ref, onMounted, provide } from 'vue'
import { getConfig } from './api'
import Dashboard from './views/Dashboard.vue'
import KLine from './views/KLine.vue'
import Filter from './views/Filter.vue'
import Settings from './views/Settings.vue'
import SymbolsView from './views/Symbols.vue'
import DataPanel from './views/DataPanel.vue'
import Learn from './views/Learn.vue'

const activeTab = ref('dashboard')
const cfg = ref(null)

provide('cfg', cfg)

async function reloadCfg() {
  cfg.value = (await getConfig()).data
}

onMounted(reloadCfg)
</script>

<template>
  <div class="layout">
    <header class="header">
      <div class="logo">
        <span class="logo-icon">⚡</span>
        <div class="logo-text">
          <div class="title">K7Quant</div>
          <div class="subtitle">币安量化回测系统 v3.0</div>
        </div>
      </div>
      <nav class="nav">
        <button :class="{ active: activeTab === 'dashboard' }" @click="activeTab = 'dashboard'">🎯 智能回测</button>
        <button :class="{ active: activeTab === 'kline' }" @click="activeTab = 'kline'">📊 K线数据</button>
        <button :class="{ active: activeTab === 'filter' }" @click="activeTab = 'filter'">🔍 币种筛选</button>
        <button :class="{ active: activeTab === 'symbols' }" @click="activeTab = 'symbols'">💎 币种库</button>
        <button :class="{ active: activeTab === 'data' }" @click="activeTab = 'data'">💾 数据缓存</button>
        <button :class="{ active: activeTab === 'settings' }" @click="activeTab = 'settings'">⚙️ 配置中心</button>
        <button :class="{ active: activeTab === 'learn' }" @click="activeTab = 'learn'">📚 量化课堂</button>
      </nav>
      <div class="status" v-if="cfg">
        <span class="badge yellow">{{ cfg.settings.active_symbols.length }} 活跃</span>
        <span class="badge">{{ cfg.symbols.length }} 总池</span>
      </div>
    </header>

    <main class="main">
      <Dashboard v-if="activeTab === 'dashboard' && cfg" :cfg="cfg" :reload="reloadCfg" />
      <KLine v-else-if="activeTab === 'kline' && cfg" :cfg="cfg" />
      <Filter v-else-if="activeTab === 'filter' && cfg" :cfg="cfg" />
      <SymbolsView v-else-if="activeTab === 'symbols' && cfg" :cfg="cfg" :reload="reloadCfg" />
      <DataPanel v-else-if="activeTab === 'data'" />
      <Settings v-else-if="activeTab === 'settings' && cfg" :cfg="cfg" :reload="reloadCfg" />
      <Learn v-else-if="activeTab === 'learn'" :cfg="cfg" />
      <div v-else class="loading">加载中...</div>
    </main>
  </div>
</template>

<style scoped>
.layout { min-height: 100vh; display: flex; flex-direction: column; }
.header {
  background: #181a20;
  border-bottom: 1px solid var(--binance-border);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 20px;
  position: sticky;
  top: 0;
  z-index: 10;
  flex-wrap: wrap;
}
.logo { display: flex; align-items: center; gap: 10px; min-width: 200px; }
.logo-icon { font-size: 26px; color: var(--binance-yellow); }
.logo-text .title { font-size: 18px; font-weight: 700; color: var(--binance-yellow); letter-spacing: 1px; }
.logo-text .subtitle { font-size: 11px; color: var(--binance-text-secondary); }
.nav { display: flex; gap: 2px; flex: 1; flex-wrap: wrap; }
.nav button {
  background: transparent;
  color: var(--binance-text-secondary);
  padding: 7px 12px;
  border-radius: 6px;
  font-size: 12px;
  transition: all 0.2s;
}
.nav button:hover { color: var(--binance-text); background: #2b3139; }
.nav button.active { color: var(--binance-yellow); background: #2b3139; }
.status { display: flex; gap: 6px; }
.badge {
  background: #2b3139;
  color: var(--binance-text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-family: 'Consolas', monospace;
}
.badge.yellow { background: #f0b90b22; color: var(--binance-yellow); border: 1px solid #f0b90b44; }
.main {
  flex: 1;
  padding: 20px;
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