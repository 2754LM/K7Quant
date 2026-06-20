<script setup>
import { ref, computed } from 'vue'
import {
  setActiveSymbols, setStrategyDefaults, setBacktestDefaults, setTimeframes, resetConfig,
} from '../api'

const props = defineProps({ cfg: Object, reload: Function })

const tab = ref('backtest')
const saving = ref(false)
const msg = ref('')

// 本地副本（避免修改时频繁触发后端）
const btDefaults = ref({ ...props.cfg.settings.backtest })
const symbols = ref(new Set(props.cfg.settings.active_symbols))
const tfs = ref(new Set(props.cfg.settings.timeframes))
const strategyParams = ref(JSON.parse(JSON.stringify(props.cfg.settings.strategy_defaults)))

const symbolInfo = computed(() => {
  const m = {}
  for (const s of props.cfg?.symbols || []) m[s.symbol] = s
  return m
})

function showMsg(text, isErr = false) {
  msg.value = (isErr ? '✗ ' : '✓ ') + text
  setTimeout(() => msg.value = '', 3000)
}

async function saveBacktest() {
  saving.value = true
  try {
    await setBacktestDefaults(btDefaults.value)
    showMsg('回测默认值已保存')
    await props.reload?.()
  } catch (e) { showMsg(e.message, true) }
  finally { saving.value = false }
}

async function saveSymbols() {
  saving.value = true
  try {
    await setActiveSymbols([...symbols.value])
    showMsg('活跃币种已保存')
    await props.reload?.()
  } catch (e) { showMsg(e.message, true) }
  finally { saving.value = false }
}

function toggleSymbol(s) {
  if (symbols.value.has(s)) symbols.value.delete(s)
  else symbols.value.add(s)
}

function toggleTf(t) {
  if (tfs.value.has(t)) tfs.value.delete(t)
  else tfs.value.add(t)
}

async function saveTfs() {
  saving.value = true
  try {
    await setTimeframes([...tfs.value].sort())
    showMsg('K线周期已保存')
    await props.reload?.()
  } catch (e) { showMsg(e.message, true) }
  finally { saving.value = false }
}

async function saveStrategyParams(sid) {
  saving.value = true
  try {
    await setStrategyDefaults(sid, strategyParams.value[sid])
    showMsg(`${sid} 参数已保存`)
    await props.reload?.()
  } catch (e) { showMsg(e.message, true) }
  finally { saving.value = false }
}

async function resetAll() {
  if (!confirm('确认重置所有配置为默认值？')) return
  await resetConfig()
  await props.reload?.()
  btDefaults.value = { ...props.cfg.settings.backtest }
  symbols.value = new Set(props.cfg.settings.active_symbols)
  tfs.value = new Set(props.cfg.settings.timeframes)
  strategyParams.value = JSON.parse(JSON.stringify(props.cfg.settings.strategy_defaults))
  showMsg('已重置为默认')
}

const ALL_TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '1w']
</script>

<template>
  <div class="settings-view">
    <div class="tabs">
      <button :class="{ active: tab === 'backtest' }" @click="tab = 'backtest'">回测默认值</button>
      <button :class="{ active: tab === 'symbols' }" @click="tab = 'symbols'">活跃币种</button>
      <button :class="{ active: tab === 'timeframes' }" @click="tab = 'timeframes'">K线周期</button>
      <button :class="{ active: tab === 'strategies' }" @click="tab = 'strategies'">策略参数</button>
      <button :class="{ active: tab === 'about' }" @click="tab = 'about'">关于</button>
      <div class="spacer"></div>
      <button class="reset-btn" @click="resetAll">重置全部</button>
      <span v-if="msg" class="msg">{{ msg }}</span>
    </div>

    <!-- 回测默认值 -->
    <div v-if="tab === 'backtest'" class="card">
      <h3>回测默认参数</h3>
      <p class="hint">修改后点保存生效，智能回测页会使用这里的默认值</p>
      <div class="form-grid">
        <div class="form-row">
          <label>初始资金 (USDT)</label>
          <input type="number" v-model.number="btDefaults.initial_capital" />
        </div>
        <div class="form-row">
          <label>手续费率</label>
          <input type="number" v-model.number="btDefaults.commission" step="0.0001" />
          <span class="hint">Binance 现货默认 0.0004</span>
        </div>
        <div class="form-row">
          <label>默认杠杆</label>
          <select v-model.number="btDefaults.leverage">
            <option v-for="x in [1,2,3,5,10]" :key="x" :value="x">{{ x }}x</option>
          </select>
        </div>
        <div class="form-row">
          <label>默认 K 线</label>
          <select v-model="btDefaults.default_timeframe">
            <option v-for="t in ALL_TIMEFRAMES" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>开始日期 (YYYYMMDD)</label>
          <input type="text" v-model="btDefaults.start_date" />
        </div>
        <div class="form-row">
          <label>结束日期</label>
          <input type="text" v-model="btDefaults.end_date" />
          <span class="hint">输入 "auto" 跟随当前日期</span>
        </div>
      </div>
      <button class="save-btn" :disabled="saving" @click="saveBacktest">保存</button>
    </div>

    <!-- 活跃币种 -->
    <div v-if="tab === 'symbols'" class="card">
      <h3>活跃币种池</h3>
      <p class="hint">这里选的币种在「智能回测」「筛选」中作为默认池（{{ symbols.size }} / {{ cfg.symbols.length }}）</p>
      <div class="symbol-grid">
        <button v-for="s in cfg.symbols" :key="s.symbol"
          :class="['sym-btn', { active: symbols.has(s.symbol) }]"
          @click="toggleSymbol(s.symbol)">
          <div class="name">{{ s.name_zh }}</div>
          <div class="code">{{ s.symbol }}</div>
        </button>
      </div>
      <button class="save-btn" :disabled="saving" @click="saveSymbols">保存</button>
    </div>

    <!-- K线周期 -->
    <div v-if="tab === 'timeframes'" class="card">
      <h3>K 线周期</h3>
      <p class="hint">勾选可用的 K 线周期，未勾选的会在选择器中隐藏</p>
      <div class="tf-grid">
        <label v-for="t in ALL_TIMEFRAMES" :key="t" class="tf-item" :class="{ active: tfs.has(t) }">
          <input type="checkbox" :checked="tfs.has(t)" @change="toggleTf(t)" />
          <span class="tf-label">{{ t }}</span>
        </label>
      </div>
      <button class="save-btn" :disabled="saving" @click="saveTfs">保存</button>
    </div>

    <!-- 策略参数 -->
    <div v-if="tab === 'strategies'" class="card">
      <h3>策略默认参数</h3>
      <p class="hint">每个策略的默认值，切换策略时会自动套用</p>
      <div v-for="s in cfg.strategies" :key="s.id" class="strategy-block">
        <div class="strategy-header">
          <h4>{{ s.icon }} {{ s.name }} <span class="cat">({{ s.category }})</span></h4>
          <p class="strategy-desc">{{ s.description }}</p>
        </div>
        <div class="form-grid">
          <div v-for="(schema, key) in s.params_schema" :key="key" class="form-row">
            <label>{{ schema.label }} ({{ key }})</label>
            <input type="number"
              v-model.number="strategyParams[s.id][key]"
              :min="schema.min" :max="schema.max" :step="schema.step || 1" />
          </div>
        </div>
        <button class="save-btn small" :disabled="saving" @click="saveStrategyParams(s.id)">
          保存 {{ s.name }} 参数
        </button>
      </div>
    </div>

    <!-- 关于 -->
    <div v-if="tab === 'about'" class="card">
      <h3>关于 K7Quant</h3>
      <div class="about">
        <p><strong>版本</strong>: 3.0</p>
        <p><strong>数据源</strong>: {{ cfg.settings.data_source.exchange }} ({{ cfg.settings.data_source.api_base }})</p>
        <p><strong>币种池</strong>: {{ cfg.symbols.length }} 个</p>
        <p><strong>内置策略</strong>: {{ cfg.strategies.length }} 个</p>
        <p><strong>配置文件</strong>:
          <code>config/settings.yaml</code> ·
          <code>config/symbols.yaml</code>
        </p>
        <p class="links">
          <a href="https://github.com/2754LM/K7Quant" target="_blank">GitHub</a>
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-view { display: flex; flex-direction: column; gap: 16px; }
.tabs {
  display: flex;
  gap: 4px;
  background: var(--binance-card);
  border: 1px solid var(--binance-border);
  border-radius: 12px;
  padding: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.tabs button {
  background: transparent;
  color: var(--binance-text-secondary);
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
}
.tabs button:hover { background: #2b3139; }
.tabs button.active { background: var(--binance-yellow); color: #0b0e11; font-weight: 600; }
.spacer { flex: 1; }
.reset-btn {
  background: transparent;
  color: #f6465d;
  border: 1px solid #f6465d;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
}
.reset-btn:hover { background: #f6465d22; }
.msg {
  font-size: 13px;
  color: var(--binance-green);
  padding: 0 8px;
}

.card {
  background: var(--binance-card);
  border: 1px solid var(--binance-border);
  border-radius: 12px;
  padding: 24px;
}
.card h3 { font-size: 16px; margin-bottom: 6px; }
.card .hint { font-size: 12px; color: var(--binance-text-secondary); margin-bottom: 20px; }

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row label { font-size: 12px; color: var(--binance-text-secondary); }
.form-row input, .form-row select {
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  color: var(--binance-text);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.form-row input:focus, .form-row select:focus { border-color: var(--binance-yellow); }
.form-row .hint { font-size: 11px; color: #707684; margin: 4px 0 0; }

.save-btn {
  background: var(--binance-yellow);
  color: #0b0e11;
  padding: 10px 24px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 13px;
}
.save-btn.small { padding: 6px 14px; font-size: 12px; }
.save-btn:disabled { opacity: 0.6; }

.symbol-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
  margin-bottom: 16px;
}
.sym-btn {
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  padding: 10px;
  border-radius: 6px;
  text-align: left;
  cursor: pointer;
}
.sym-btn:hover { border-color: var(--binance-yellow); }
.sym-btn.active { background: #f0b90b11; border-color: var(--binance-yellow); }
.sym-btn .name { font-size: 13px; font-weight: 600; }
.sym-btn .code { font-size: 11px; color: var(--binance-yellow); font-family: 'Consolas', monospace; }

.tf-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
  margin-bottom: 16px;
}
.tf-item {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
}
.tf-item.active { border-color: var(--binance-yellow); }
.tf-label { font-family: 'Consolas', monospace; font-size: 13px; }

.strategy-block {
  background: #0b0e11;
  border: 1px solid var(--binance-border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
}
.strategy-header { margin-bottom: 16px; }
.strategy-header h4 { font-size: 16px; color: var(--binance-yellow); margin-bottom: 4px; }
.strategy-header .cat {
  font-size: 11px;
  color: var(--binance-text-secondary);
  font-family: 'Consolas', monospace;
  margin-left: 8px;
}
.strategy-desc { font-size: 12px; color: var(--binance-text-secondary); }

.about p { font-size: 14px; line-height: 2; }
.about code {
  background: #0b0e11;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', monospace;
  color: var(--binance-yellow);
}
.about .links a { color: var(--binance-yellow); }
</style>