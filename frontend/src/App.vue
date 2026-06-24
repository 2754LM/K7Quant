<script setup>
import { ref, computed, onMounted, onUnmounted, provide, defineAsyncComponent } from 'vue'
import { NConfigProvider, NMessageProvider, NDialogProvider, darkTheme } from 'naive-ui'
import { getConfig, listSymbols, getStrategies } from './api'
import SystemLogPanel from './components/SystemLogPanel.vue'
import { _startBackendLogPolling, _stopBackendLogPolling, info as logInfo } from './utils/systemLog'

// 视图懒加载: 各 Tab 按需加载, 减小初始 bundle
// 注: defineAsyncComponent 必须在 setup 顶部, 否则 Vite 不会做 chunk 拆分
const Dashboard = defineAsyncComponent(() => import('./views/Dashboard.vue'))
const KLine = defineAsyncComponent(() => import('./views/KLine.vue'))
const Filter = defineAsyncComponent(() => import('./views/Filter.vue'))
const Strategy = defineAsyncComponent(() => import('./views/Strategy.vue'))
const Factor = defineAsyncComponent(() => import('./views/Factor.vue'))
const Symbols = defineAsyncComponent(() => import('./views/Symbols.vue'))
const DataPanel = defineAsyncComponent(() => import('./views/DataPanel.vue'))
const Settings = defineAsyncComponent(() => import('./views/Settings.vue'))
const Trade = defineAsyncComponent(() => import('./views/Trade.vue'))
const Learn = defineAsyncComponent(() => import('./views/Learn.vue'))
const LogViewer = defineAsyncComponent(() => import('./views/LogViewer.vue'))
const Verify = defineAsyncComponent(() => import('./views/Verify.vue'))

const themeOverrides = {
  common: {
    primaryColor: '#f0b90b',
    primaryColorHover: '#fcd535',
    primaryColorPressed: '#d8a200',
    primaryColorSuppl: '#f0b90b',
    bodyColor: '#181a20',
    cardColor: '#1e2329',
    modalColor: '#1e2329',
    popoverColor: '#1e2329',
    borderColor: '#2b3139',
    dividerColor: '#2b3139',
    textColorBase: '#eaecef',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  },
}

const cfg = ref(null)
const symbolCount = ref(0)
const strategyCount = ref(0)

// 可扩展 Tab 注册表: 新增页面只需往这里 push 一行 (id/label/组件/是否需要 cfg/reload)
const TABS = [
  { id: 'dashboard', label: '🎯 智能回测', comp: Dashboard, needsCfg: true },
  { id: 'kline', label: '📊 K线数据', comp: KLine, needsCfg: true },
  { id: 'factor', label: '🔬 因子', comp: Factor, needsCfg: true },
  { id: 'filter', label: '🔍 币种筛选', comp: Filter, needsCfg: true },
  { id: 'symbols', label: '💎 币种库', comp: Symbols, needsCfg: true, needsReload: true },
  { id: 'strategy', label: '🛠️ 自写策略', comp: Strategy, needsCfg: true },
  { id: 'data', label: '💾 数据', comp: DataPanel },
  { id: 'trade', label: '📈 模拟/实盘', comp: Trade },
  { id: 'settings', label: '⚙️ 设置', comp: Settings, needsCfg: true, needsReload: true },
  { id: 'learn', label: '📚 课堂', comp: Learn, needsCfg: true },
  { id: 'verify', label: '✅ 验证', comp: Verify, needsCfg: false },
  { id: 'logs', label: '📋 日志', comp: LogViewer, needsCfg: false },
]

const activeTab = ref('dashboard')
const active = computed(() => TABS.find(t => t.id === activeTab.value) || TABS[0])
const ready = computed(() => !active.value.needsCfg || !!cfg.value)
const activeProps = computed(() => {
  const p = {}
  if (active.value.needsCfg) p.cfg = cfg.value
  if (active.value.needsReload) p.reload = reloadCfg
  return p
})

function applyUi() {
  // 启动即按用户偏好套用主题/问号提示, 不再依赖打开"设置"页才生效
  const settings = (cfg.value && cfg.value.settings) || {}
  const ui = settings.ui || {}
  document.documentElement.setAttribute('data-theme', ui.theme || 'dark')
  document.documentElement.setAttribute('data-show-tooltips', String(ui.show_help_tooltips ?? true))
}

async function reloadCfg() {
  try {
    const res = await getConfig()
    cfg.value = res.data
    applyUi()
    // 头部统计 (config 接口不含数量, 单独取)
    const [syms, strats] = await Promise.all([listSymbols(), getStrategies()])
    symbolCount.value = syms.data.symbols.length
    strategyCount.value = strats.data.strategies.length
  } catch (e) {
    console.error(e)
  }
}

provide('cfg', cfg)
provide('reload', reloadCfg)

function navigate(event) {
  const target = event.detail
  if (target === 'logs') activeTab.value = 'logs'
}
onMounted(() => {
  reloadCfg()
  window.addEventListener('navigate', navigate)
  // 后端日志轮询: 拉 logs/app.log 最近行, 解析后塞进 systemLog
  _startBackendLogPolling(3000)
  logInfo('system', '前端启动, 后端日志轮询已开启 (3s)')
})
onUnmounted(() => {
  window.removeEventListener('navigate', navigate)
  _stopBackendLogPolling()
})
</script>

<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <div class="layout">
          <header class="header">
            <div class="logo">
              <span class="logo-icon">⚡</span>
              <div class="logo-text">
                <div class="title">K7Quant</div>
                <div class="subtitle">币安量化回测系统 v4.0</div>
              </div>
            </div>
            <nav class="nav">
              <button v-for="t in TABS" :key="t.id"
                :class="{ active: activeTab === t.id }"
                @click="activeTab = t.id">{{ t.label }}</button>
            </nav>
            <div class="status">
              <span class="badge yellow" :title="`${symbolCount} 个币种被激活`">
                {{ (cfg?.active_symbols?.length ?? symbolCount) }} 活跃
              </span>
              <span class="badge" :title="`总币种数: ${symbolCount}`">{{ symbolCount }} 总</span>
              <span class="badge" :title="`总策略数: ${strategyCount}`">{{ strategyCount }} 策略</span>
              <SystemLogPanel />
            </div>
          </header>
          <main class="main">
            <component v-if="ready" :is="active.comp" v-bind="activeProps" />
            <div v-else class="loading-screen">
              <div class="spinner"></div>
              <span>正在加载配置...</span>
            </div>
          </main>
        </div>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
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
.loading-screen {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 100px 0;
  gap: 16px;
  color: var(--text-secondary);
}
.loading-screen .spinner {
  width: 40px; height: 40px;
  border: 3px solid var(--border);
  border-top-color: var(--yellow);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
