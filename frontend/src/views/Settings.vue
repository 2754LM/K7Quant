<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { useMessage, NSelect, NSwitch, NInputNumber, NInput, NButton, NTag, NDivider } from 'naive-ui'
import { updateBacktestConfig, updateDataSourceConfig, updateUiConfig, updateTradingConfig } from '../api'
import { success as logSuccess, error as logError } from '../utils/systemLog'

const cfg = inject('cfg')
const reloadCfg = inject('reload')
const message = useMessage()

const tab = ref('backtest')
const saving = ref(false)

const bt = ref({})
const ds = ref({})
const ui = ref({})
const tr = ref({})

const tabs = [
  { id: 'backtest', label: '回测默认值' },
  { id: 'data', label: '数据源 + VPN' },
  { id: 'ui', label: '界面 (主题/提示)' },
  { id: 'trading', label: '交易 (模拟/实盘)' },
  { id: 'about', label: '关于' },
]

const POSITION_MODE_OPTS = [
  { label: '满仓 (all_in)', value: 'all_in' },
  { label: '固定金额 (fixed_amount)', value: 'fixed_amount' },
]
const TIMEFRAME_OPTS = [
  { label: '1 分钟', value: '1m' }, { label: '5 分钟', value: '5m' },
  { label: '15 分钟', value: '15m' }, { label: '30 分钟', value: '30m' },
  { label: '1 小时', value: '1h' }, { label: '2 小时', value: '2h' },
  { label: '4 小时', value: '4h' }, { label: '12 小时', value: '12h' },
  { label: '1 天', value: '1d' }, { label: '3 天', value: '3d' }, { label: '1 周', value: '1w' },
]
const THEME_OPTS = [
  { label: '🌙 深色 (Binance 风格)', value: 'dark' },
  { label: '☀️ 浅色', value: 'light' },
]
const BOOL_OPTS_TRUE = [{ label: '是', value: true }, { label: '否', value: false }]
const TRADE_MODE_OPTS = [
  { label: '🧪 模拟盘', value: 'simulation' },
  { label: '⚠️ 实盘 (谨慎!)', value: 'live' },
]
const ENABLED_OPTS = [
  { label: '🚫 否', value: false },
  { label: '✓ 是', value: true },
]

onMounted(() => {
  const s = (cfg.value && cfg.value.settings) || {}
  bt.value = { ...(s.backtest || {}) }
  ds.value = { ...(s.data_source || {}), proxy: { ...((s.data_source || {}).proxy || {}) } }
  ui.value = { ...(s.ui || {}) }
  tr.value = { ...(s.trading || {}) }
  applyTheme()
  applyTooltips()
})

async function notify(text, type = 'success') {
  message[type](text, { duration: 2500 })
  if (type === 'success') logSuccess('settings', text)
  else logError('settings', text)
}

async function saveBt() {
  saving.value = true
  try {
    await updateBacktestConfig(bt.value)
    await notify('回测默认值已保存')
    if (reloadCfg) await reloadCfg()
  } catch (e) { await notify(e.message, 'error') }
  finally { saving.value = false }
}

async function saveDs() {
  saving.value = true
  try {
    await updateDataSourceConfig({
      api_base: ds.value.api_base,
      proxy_enabled: ds.value.proxy.enabled,
      proxy_http: ds.value.proxy.http,
      proxy_https: ds.value.proxy.https,
    })
    await notify('数据源已保存 (重启后生效)')
  } catch (e) { await notify(e.message, 'error') }
  finally { saving.value = false }
}

async function saveUi() {
  saving.value = true
  try {
    await updateUiConfig(ui.value)
    applyTheme()
    applyTooltips()
    await notify('界面设置已保存')
    if (reloadCfg) await reloadCfg()
  } catch (e) { await notify(e.message, 'error') }
  finally { saving.value = false }
}

async function saveTr() {
  saving.value = true
  try {
    await updateTradingConfig(tr.value)
    await notify('交易设置已保存')
  } catch (e) { await notify(e.message, 'error') }
  finally { saving.value = false }
}

function applyTheme() {
  document.documentElement.setAttribute('data-theme', ui.value.theme || 'dark')
}
function applyTooltips() {
  document.documentElement.setAttribute('data-show-tooltips', String(ui.value.show_help_tooltips ?? true))
}
</script>

<template>
  <div class="settings">
    <div class="tabs">
      <button v-for="t in tabs" :key="t.id"
        :class="{ active: tab === t.id }"
        @click="tab = t.id">{{ t.label }}</button>
    </div>

    <!-- 回测默认 -->
    <div v-if="tab === 'backtest'" class="card">
      <h3>📊 回测默认值</h3>
      <p class="hint">这些是智能回测的默认值, 改完保存即可</p>
      <div class="form-grid">
        <div class="form-row">
          <label>初始资金 (USDT)</label>
          <n-input-number v-model:value="bt.initial_capital" :min="100" :step="1000" />
        </div>
        <div class="form-row">
          <label>手续费率</label>
          <n-input-number v-model:value="bt.commission_rate" :step="0.0001" :precision="4" />
          <span class="hint">Binance 现货默认 0.0004 (0.04%)</span>
        </div>
        <div class="form-row">
          <label>滑点 (估算)</label>
          <n-input-number v-model:value="bt.slippage" :step="0.0001" :precision="4" />
        </div>
        <div class="form-row">
          <label>调仓频率 (每 N 根换仓)</label>
          <n-input-number v-model:value="bt.rebalance_bars" :min="1" :step="1" />
          <span class="hint">1=每根都可换仓; N=每 N 根才换一次</span>
        </div>
        <div class="form-row">
          <label>仓位模式</label>
          <n-select v-model:value="bt.position_mode" :options="POSITION_MODE_OPTS" />
        </div>
        <div class="form-row">
          <label>固定金额 (USDT)</label>
          <n-input-number v-model:value="bt.fixed_amount" :min="0" :step="100" />
        </div>
        <div class="form-row">
          <label>默认 K 线</label>
          <n-select v-model:value="bt.default_timeframe" :options="TIMEFRAME_OPTS" />
        </div>
        <div class="form-row">
          <label>默认开始日期</label>
          <n-input v-model:value="bt.start_date" placeholder="YYYYMMDD" />
          <span class="hint">「智能回测」页面打开时使用此值作为起始, 之后用户可自行修改</span>
        </div>
        <div class="form-row">
          <label>默认结束日期</label>
          <n-input v-model:value="bt.end_date" placeholder="YYYYMMDD 或 auto" />
          <span class="hint">"auto" 跟随当前日期; 同样作为「智能回测」页面的默认值</span>
        </div>
      </div>
      <n-button type="primary" @click="saveBt" :loading="saving">保存</n-button>
    </div>

    <!-- 数据源 + VPN -->
    <div v-if="tab === 'data'" class="card">
      <h3>🌐 数据源 + VPN 配置</h3>
      <p class="hint">Binance API 在国内需要走代理. 开启后所有请求走代理</p>
      <div class="form-grid">
        <div class="form-row span-2">
          <label>API 地址</label>
          <n-input v-model:value="ds.api_base" placeholder="https://api.binance.com" />
        </div>
        <div class="form-row">
          <label>启用代理</label>
          <n-select v-model:value="ds.proxy.enabled" :options="BOOL_OPTS_TRUE" />
        </div>
        <div class="form-row">
          <label>HTTP 代理</label>
          <n-input v-model:value="ds.proxy.http" placeholder="http://127.0.0.1:7890" />
        </div>
        <div class="form-row">
          <label>HTTPS 代理</label>
          <n-input v-model:value="ds.proxy.https" placeholder="http://127.0.0.1:7890" />
          <span class="hint">Clash 默认 7890</span>
        </div>
      </div>
      <n-button type="primary" @click="saveDs" :loading="saving">保存</n-button>
    </div>

    <!-- 界面 -->
    <div v-if="tab === 'ui'" class="card">
      <h3>🎨 界面</h3>
      <div class="form-grid">
        <div class="form-row">
          <label>主题</label>
          <n-select v-model:value="ui.theme" :options="THEME_OPTS" />
        </div>
        <div class="form-row">
          <label>显示问号提示</label>
          <n-select v-model:value="ui.show_help_tooltips" :options="BOOL_OPTS_TRUE" />
          <span class="hint">关闭后所有问号提示消失</span>
        </div>
      </div>
      <n-button type="primary" @click="saveUi" :loading="saving">保存</n-button>
    </div>

    <!-- 交易 -->
    <div v-if="tab === 'trading'" class="card">
      <h3>💹 交易设置 <n-tag type="warning" size="small" round>占位</n-tag></h3>
      <p class="hint">⚠️ 模拟/实盘功能尚未实装, 这里只是预存配置</p>
      <div class="form-grid">
        <div class="form-row">
          <label>启用</label>
          <n-select v-model:value="tr.enabled" :options="ENABLED_OPTS" />
        </div>
        <div class="form-row">
          <label>模式</label>
          <n-select v-model:value="tr.mode" :options="TRADE_MODE_OPTS" />
        </div>
        <div class="form-row">
          <label>单币最大仓位 %</label>
          <n-input-number v-model:value="tr.max_position_pct" :step="0.05" :min="0" :max="1" :precision="2" />
        </div>
        <div class="form-row">
          <label>总仓位 %</label>
          <n-input-number v-model:value="tr.max_total_pct" :step="0.05" :min="0" :max="1" :precision="2" />
        </div>
        <div class="form-row">
          <label>止损 %</label>
          <n-input-number v-model:value="tr.stop_loss_pct" :step="0.01" :min="0" :max="0.5" :precision="3" />
        </div>
        <div class="form-row">
          <label>止盈 %</label>
          <n-input-number v-model:value="tr.take_profit_pct" :step="0.01" :min="0" :max="1" :precision="3" />
        </div>
      </div>
      <n-button type="primary" @click="saveTr" :loading="saving">保存</n-button>
    </div>

    <!-- 关于 -->
    <div v-if="tab === 'about'" class="card">
      <h3>ℹ️ 关于 K7Quant</h3>
      <div class="about">
        <p><strong>版本:</strong> 3.0 (2026-06)</p>
        <p><strong>数据源:</strong> {{ (cfg?.settings?.data_source?.exchange) }} ({{ (cfg?.settings?.data_source?.api_base) }})</p>
        <p><strong>币种池:</strong> {{ cfg?.symbols?.length || 0 }} 个</p>
        <p><strong>内置策略:</strong> {{ cfg?.strategies?.length || 0 }} 个</p>
        <p><strong>配置文件:</strong> <code>config.yaml</code></p>
        <p><strong>GitHub:</strong> <a href="https://github.com/2754LM/K7Quant" target="_blank">https://github.com/2754LM/K7Quant</a></p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings { display: flex; flex-direction: column; gap: 16px; }
.tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.tabs button {
  background: transparent;
  color: var(--text-secondary);
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
}
.tabs button:hover { background: var(--bg-elevated); }
.tabs button.active { background: var(--yellow); color: #000; font-weight: 600; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
}
.card h3 { font-size: 16px; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.card .hint { font-size: 12px; color: var(--text-secondary); margin-bottom: 20px; }
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row.span-2 { grid-column: span 2; }
.form-row label { font-size: 12px; color: var(--text-secondary); }
.form-row .hint { font-size: 11px; color: var(--text-muted); margin: 4px 0 0; }
.about p { font-size: 14px; line-height: 2; color: var(--text); }
.about code {
  background: var(--bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', monospace;
  color: var(--yellow);
}
.about a { color: var(--yellow); }
@media (max-width: 900px) {
  .form-grid { grid-template-columns: 1fr; }
  .form-row.span-2 { grid-column: span 1; }
}
</style>
