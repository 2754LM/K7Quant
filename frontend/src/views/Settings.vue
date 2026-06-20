<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { getSystemConfig, updateBacktestConfig, updateDataSourceConfig, updateUiConfig, updateTradingConfig } from '../api'
import StateView from '../components/StateView.vue'

const cfg = inject('cfg')
const reloadCfg = inject('reload')

const tab = ref('backtest')
const saving = ref(false)
const msg = ref('')

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

onMounted(() => {
  const s = (cfg.value && cfg.value.settings) || {}
  bt.value = { ...(s.backtest || {}) }
  ds.value = { ...(s.data_source || {}), proxy: { ...((s.data_source || {}).proxy || {}) } }
  ui.value = { ...(s.ui || {}) }
  tr.value = { ...(s.trading || {}) }
})

async function showMsg(text, isErr = false) {
  msg.value = (isErr ? '✗ ' : '✓ ') + text
  setTimeout(() => msg.value = '', 3000)
}

async function saveBt() {
  saving.value = true
  try {
    await updateBacktestConfig(bt.value)
    await showMsg('回测默认值已保存')
    if (reloadCfg) await reloadCfg()
  } catch (e) { await showMsg(e.message, true) }
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
    await showMsg('数据源已保存 (重启后生效)')
  } catch (e) { await showMsg(e.message, true) }
  finally { saving.value = false }
}
async function saveUi() {
  saving.value = true
  try {
    await updateUiConfig(ui.value)
    applyTheme()
    applyTooltips()
    await showMsg('界面设置已保存')
    if (reloadCfg) await reloadCfg()
  } catch (e) { await showMsg(e.message, true) }
  finally { saving.value = false }
}
async function saveTr() {
  saving.value = true
  try {
    await updateTradingConfig(tr.value)
    await showMsg('交易设置已保存')
  } catch (e) { await showMsg(e.message, true) }
  finally { saving.value = false }
}

function applyTheme() {
  document.documentElement.setAttribute('data-theme', ui.value.theme || 'dark')
}
function applyTooltips() {
  document.documentElement.setAttribute('data-show-tooltips', String(ui.value.show_help_tooltips ?? true))
}

onMounted(() => {
  applyTheme()
  applyTooltips()
})
</script>

<template>
  <div class="settings">
    <div class="tabs">
      <button v-for="t in tabs" :key="t.id"
        :class="{ active: tab === t.id }"
        @click="tab = t.id">{{ t.label }}</button>
      <div class="spacer"></div>
      <span v-if="msg" class="msg">{{ msg }}</span>
    </div>

    <div v-if="tab === 'backtest'" class="card">
      <h3>回测默认值</h3>
      <p class="hint">这些是智能回测的默认值, 改完保存即可</p>
      <div class="form-grid">
        <div class="form-row">
          <label>初始资金 (USDT)</label>
          <input type="number" v-model.number="bt.initial_capital" />
        </div>
        <div class="form-row">
          <label>手续费率</label>
          <input type="number" v-model.number="bt.commission_rate" step="0.0001" />
          <span class="hint">Binance 现货 0.0004</span>
        </div>
        <div class="form-row">
          <label>滑点 (估算)</label>
          <input type="number" v-model.number="bt.slippage" step="0.0001" />
        </div>
        <div class="form-row">
          <label>调仓频率 (每 N 根换仓)</label>
          <input type="number" v-model.number="bt.rebalance_bars" min="1" step="1" />
          <span class="hint">1=每根都可换仓; N=每 N 根才换一次 (降频)</span>
        </div>
        <div class="form-row">
          <label>仓位模式</label>
          <select v-model="bt.position_mode">
            <option value="all_in">满仓 (all_in)</option>
            <option value="fixed_amount">固定金额 (fixed_amount)</option>
          </select>
          <span class="hint">满仓=全部本金, 固定=用 fixed_amount</span>
        </div>
        <div class="form-row">
          <label>固定金额 (USDT)</label>
          <input type="number" v-model.number="bt.fixed_amount" />
        </div>
        <div class="form-row">
          <label>默认 K 线</label>
          <input type="text" v-model="bt.default_timeframe" />
        </div>
        <div class="form-row">
          <label>开始日期 (YYYYMMDD)</label>
          <input type="text" v-model="bt.start_date" />
        </div>
        <div class="form-row">
          <label>结束日期</label>
          <input type="text" v-model="bt.end_date" />
          <span class="hint">"auto" 跟随当前日期</span>
        </div>
      </div>
      <button class="btn-primary" @click="saveBt" :disabled="saving">保存</button>
    </div>

    <div v-if="tab === 'data'" class="card">
      <h3>数据源 + VPN 配置</h3>
      <p class="hint">Binance API 在国内需要走代理. 开启后所有请求走代理</p>
      <div class="form-grid">
        <div class="form-row">
          <label>API 地址</label>
          <input type="text" v-model="ds.api_base" />
        </div>
        <div class="form-row">
          <label>启用代理</label>
          <select v-model="ds.proxy.enabled">
            <option :value="true">是</option>
            <option :value="false">否</option>
          </select>
        </div>
        <div class="form-row">
          <label>HTTP 代理</label>
          <input type="text" v-model="ds.proxy.http" placeholder="http://127.0.0.1:7890" />
        </div>
        <div class="form-row">
          <label>HTTPS 代理</label>
          <input type="text" v-model="ds.proxy.https" placeholder="http://127.0.0.1:7890" />
          <span class="hint">Clash 默认 7890</span>
        </div>
      </div>
      <button class="btn-primary" @click="saveDs" :disabled="saving">保存</button>
    </div>

    <div v-if="tab === 'ui'" class="card">
      <h3>界面</h3>
      <div class="form-grid">
        <div class="form-row">
          <label>主题</label>
          <select v-model="ui.theme">
            <option value="dark">深色 (Binance 风格)</option>
            <option value="light">浅色</option>
          </select>
        </div>
        <div class="form-row">
          <label>显示问号提示</label>
          <select v-model="ui.show_help_tooltips">
            <option :value="true">显示</option>
            <option :value="false">隐藏</option>
          </select>
          <span class="hint">关闭后所有问号提示消失</span>
        </div>
      </div>
      <button class="btn-primary" @click="saveUi" :disabled="saving">保存</button>
    </div>

    <div v-if="tab === 'trading'" class="card">
      <h3>交易设置 (占位)</h3>
      <p class="hint">⚠️ 模拟/实盘功能尚未实装, 这里只是预存配置</p>
      <div class="form-grid">
        <div class="form-row">
          <label>启用</label>
          <select v-model="tr.enabled">
            <option :value="false">否</option>
            <option :value="true">是 (谨慎!)</option>
          </select>
        </div>
        <div class="form-row">
          <label>模式</label>
          <select v-model="tr.mode">
            <option value="simulation">模拟盘</option>
            <option value="live">实盘</option>
          </select>
        </div>
        <div class="form-row">
          <label>单币最大仓位 %</label>
          <input type="number" v-model.number="tr.max_position_pct" step="0.05" min="0" max="1" />
        </div>
        <div class="form-row">
          <label>总仓位 %</label>
          <input type="number" v-model.number="tr.max_total_pct" step="0.05" min="0" max="1" />
        </div>
        <div class="form-row">
          <label>止损 %</label>
          <input type="number" v-model.number="tr.stop_loss_pct" step="0.01" min="0" max="0.5" />
        </div>
        <div class="form-row">
          <label>止盈 %</label>
          <input type="number" v-model.number="tr.take_profit_pct" step="0.01" min="0" max="1" />
        </div>
      </div>
      <button class="btn-primary" @click="saveTr" :disabled="saving">保存</button>
    </div>

    <div v-if="tab === 'about'" class="card">
      <h3>关于 K7Quant</h3>
      <div class="about">
        <p><strong>版本:</strong> 3.0 (2026-06)</p>
        <p><strong>数据源:</strong> {{ cfg?.data_source?.exchange }} ({{ cfg?.data_source?.api_base }})</p>
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
.spacer { flex: 1; }
.msg { font-size: 13px; color: var(--green); padding: 0 8px; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
}
.card h3 { font-size: 16px; margin-bottom: 8px; }
.card .hint { font-size: 12px; color: var(--text-secondary); margin-bottom: 20px; }
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row label { font-size: 12px; color: var(--text-secondary); }
.form-row input, .form-row select {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.form-row input:focus, .form-row select:focus { border-color: var(--yellow); }
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
</style>