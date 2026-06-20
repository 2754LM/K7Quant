<script setup>
import { ref, onMounted, provide } from 'vue'
import { getConfig } from './api'
import Dashboard from './views/Dashboard.vue'
import KLine from './views/KLine.vue'
import Filter from './views/Filter.vue'
import Strategy from './views/Strategy.vue'
import Factor from './views/Factor.vue'
import Symbols from './views/Symbols.vue'
import DataPanel from './views/DataPanel.vue'
import Settings from './views/Settings.vue'
import Trade from './views/Trade.vue'
import Learn from './views/Learn.vue'

const activeTab = ref('dashboard')
const cfg = ref(null)

async function reloadCfg() {
  try {
    const res = await getConfig()
    cfg.value = res.data
  } catch (e) {
    console.error(e)
  }
}

provide('cfg', cfg)
provide('reload', reloadCfg)

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
        <button :class="{ active: activeTab === 'factor' }" @click="activeTab = 'factor'">🔬 因子</button>
        <button :class="{ active: activeTab === 'filter' }" @click="activeTab = 'filter'">🔍 币种筛选</button>
        <button :class="{ active: activeTab === 'symbols' }" @click="activeTab = 'symbols'">💎 币种库</button>
        <button :class="{ active: activeTab === 'strategy' }" @click="activeTab = 'strategy'">🛠️ 自写策略</button>
        <button :class="{ active: activeTab === 'data' }" @click="activeTab = 'data'">💾 数据</button>
        <button :class="{ active: activeTab === 'trade' }" @click="activeTab = 'trade'">📈 模拟/实盘</button>
        <button :class="{ active: activeTab === 'settings' }" @click="activeTab = 'settings'">⚙️ 设置</button>
        <button :class="{ active: activeTab === 'learn' }" @click="activeTab = 'learn'">📚 课堂</button>
      </nav>
      <div class="status" v-if="cfg">
        <span class="badge yellow">{{ cfg.settings.active_symbols.length }} 活跃</span>
        <span class="badge">{{ cfg.symbols.length }} 总</span>
        <span class="badge">{{ cfg.strategies.length }} 策略</span>
      </div>
    </header>

    <main class="main">
      <Dashboard v-if="activeTab === 'dashboard' && cfg" :cfg="cfg" />
      <KLine v-else-if="activeTab === 'kline' && cfg" :cfg="cfg" />
      <Factor v-else-if="activeTab === 'factor' && cfg" :cfg="cfg" />
      <Filter v-else-if="activeTab === 'filter' && cfg" :cfg="cfg" />
      <Strategy v-else-if="activeTab === 'strategy' && cfg" :cfg="cfg" />
      <Symbols v-else-if="activeTab === 'symbols' && cfg" :cfg="cfg" :reload="reloadCfg" />
      <DataPanel v-else-if="activeTab === 'data'" />
      <Trade v-else-if="activeTab === 'trade'" />
      <Settings v-else-if="activeTab === 'settings' && cfg" :cfg="cfg" :reload="reloadCfg" />
      <Learn v-else-if="activeTab === 'learn'" :cfg="cfg" />
      <div v-else class="loading">加载中...</div>
    </main>
  </div>
</template>

<style scoped>
.layout { min-height: 100vh; display: flex; flex-direction: column; }
.header {
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  position: sticky;
  top: 0;
  z-index: 10;
  flex-wrap: wrap;
}
.logo { display: flex; align-items: center; gap: 8px; min-width: 200px; }
.logo-icon { font-size: 26px; color: var(--yellow); }
.logo-text .title { font-size: 17px; font-weight: 700; color: var(--yellow); letter-spacing: 1px; }
.logo-text .subtitle { font-size: 11px; color: var(--text-secondary); }
.nav { display: flex; gap: 2px; flex: 1; flex-wrap: wrap; }
.nav button {
  background: transparent;
  color: var(--text-secondary);
  padding: 7px 12px;
  border-radius: 6px;
  font-size: 12px;
}
.nav button:hover { color: var(--text); background: var(--bg-elevated); }
.nav button.active { color: var(--yellow); background: var(--bg-elevated); }
.status { display: flex; gap: 6px; }
.badge {
  background: var(--bg-elevated);
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-family: 'Consolas', monospace;
}
.badge.yellow { background: rgba(240,185,11,0.15); color: var(--yellow); border: 1px solid rgba(240,185,11,0.3); }
.main {
  flex: 1;
  padding: 20px;
  max-width: 1600px;
  margin: 0 auto;
  width: 100%;
}
.loading { text-align: center; padding: 100px 0; color: var(--text-secondary); }
</style>