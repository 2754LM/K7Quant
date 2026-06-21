<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { KLineChartPro } from '@klinecharts/pro'
import '@klinecharts/pro/dist/klinecharts-pro.css'
import { BinanceDatafeed } from '../utils/klinechart-datafeed'
import {
  getTradeConnectivity, getTradeStatus, getTradeAccount,
  getOpenOrders, placeOrder, cancelOrder, listTrades, listSymbols, getExchangeInfo,
} from '../api'
import { subscribeKline } from '../utils/binance-ws'
import StateView from '../components/StateView.vue'

// ---- 状态 ----
const conn = ref({})
const status = ref({})
const balances = ref([])
const openOrders = ref([])
const localTrades = ref([])
const symbols = ref([])

const loading = ref(false)
const error = ref('')
const tradesError = ref('')
const submitting = ref(false)
const toasts = ref([])   // 左下角气泡通知
let toastSeq = 0

const form = reactive({
  symbol: 'BTCUSDT', side: 'BUY', type: 'LIMIT',
  quantity: 0.001, price: null, time_in_force: 'GTC',
})

const connected = computed(() => conn.value?.credentials_valid)
const configured = computed(() => conn.value?.configured)

// 可用余额 / 成本估算 (让 -2010 余额不足一目了然)
const baseAsset = computed(() => form.symbol.replace('USDT', ''))
function freeOf(asset) {
  const b = balances.value.find((x) => x.asset === asset)
  return b ? Number(b.free) : 0
}
// 买入看 USDT, 卖出看 base 币
const availAsset = computed(() => (form.side === 'BUY' ? 'USDT' : baseAsset.value))
const availFree = computed(() => freeOf(availAsset.value))
const estCost = computed(() => {
  const q = Number(form.quantity) || 0
  const p = Number(form.price) || 0
  return form.type === 'LIMIT' ? q * p : 0
})
function fillMax() {
  if (form.side === 'SELL') form.quantity = freeOf(baseAsset.value)
}

// ---- 实时市价 + 下单精度 ----
const lastPrice = ref(0)       // 来自 Binance WS (1m 流的最新收盘)
const stepSize = ref(0.00001)  // LOT_SIZE 数量步进
const tickSize = ref(0.01)     // PRICE_FILTER 价格步进
const pct = ref(0)             // 比例滑块 0~100
let priceUnsub = null

function decimalsOf(step) {
  const s = String(step)
  if (s.includes('e') || s.includes('E')) return Math.max(0, -Math.floor(Math.log10(Number(step))))
  return s.includes('.') ? s.split('.')[1].replace(/0+$/, '').length : 0
}
function floorToStep(value, step) {
  const st = Number(step) || 0
  if (st <= 0) return value
  const n = Math.floor((value + 1e-12) / st) * st
  return Number(n.toFixed(decimalsOf(step)))
}

// 订阅当前币种实时价格 (复用图表已有的 WS 工具)
function watchPrice(ticker) {
  if (priceUnsub) { priceUnsub(); priceUnsub = null }
  lastPrice.value = 0
  priceUnsub = subscribeKline(ticker, '1m', (bar) => { lastPrice.value = bar.close })
}

// 拉该币种的下单精度 (避免 -1013 精度错误)
async function loadSymbolFilters(ticker) {
  try {
    const r = await getExchangeInfo(ticker)
    const f = r.data?.filters || {}
    stepSize.value = Number(f.LOT_SIZE?.stepSize) || stepSize.value
    tickSize.value = Number(f.PRICE_FILTER?.tickSize) || tickSize.value
  } catch {}
}

// 取当前市价填入限价
function useMarketPrice() {
  if (lastPrice.value > 0) form.price = floorToStep(lastPrice.value, tickSize.value)
}

// 按持仓/资金比例计算下单数量
function applyPct(p) {
  pct.value = p
  const refPrice = form.type === 'LIMIT' ? (Number(form.price) || lastPrice.value) : lastPrice.value
  if (form.side === 'BUY') {
    if (!refPrice) return flash('error', '等待行情价格, 稍候再试 (或先填限价)')
    const budget = freeOf('USDT') * (p / 100)
    form.quantity = floorToStep(budget / refPrice, stepSize.value)
  } else {
    form.quantity = floorToStep(freeOf(baseAsset.value) * (p / 100), stepSize.value)
  }
}

// ---- 图表 ----
const chartEl = ref(null)
let chart = null
let datafeed = null

const PERIODS = [
  { multiplier: 1, timespan: 'minute', text: '1m' },
  { multiplier: 5, timespan: 'minute', text: '5m' },
  { multiplier: 15, timespan: 'minute', text: '15m' },
  { multiplier: 1, timespan: 'hour', text: '1h' },
  { multiplier: 4, timespan: 'hour', text: '4h' },
  { multiplier: 1, timespan: 'day', text: '1D' },
  { multiplier: 1, timespan: 'week', text: '1W' },
]

function symbolInfo(ticker) {
  const s = symbols.value.find((x) => x.symbol === ticker)
  return {
    ticker,
    name: s?.name_zh || ticker,
    shortName: ticker.replace('USDT', ''),
    exchange: 'Binance', market: 'spot',
    pricePrecision: 2, volumePrecision: 4, priceCurrency: 'USDT', type: 'ADRC',
  }
}

function initChart() {
  if (!chartEl.value || chart) return
  datafeed = new BinanceDatafeed()
  chart = new KLineChartPro({
    container: chartEl.value,
    locale: 'zh-CN',
    theme: 'dark',
    symbol: symbolInfo(form.symbol),
    period: { multiplier: 1, timespan: 'hour', text: '1h' },
    periods: PERIODS,
    mainIndicators: ['MA'],
    subIndicators: ['VOL'],
    datafeed,
  })
}

function changeSymbol(ticker) {
  form.symbol = ticker
  pct.value = 0
  if (chart) chart.setSymbol(symbolInfo(ticker))
  watchPrice(ticker)
  loadSymbolFilters(ticker)
}

// 下单实际用的币种: 以图表当前展示的为准 (Pro 内置搜索也能改)
function activeSymbol() {
  try { return chart?.getSymbol()?.ticker || form.symbol } catch { return form.symbol }
}

// ---- 数据加载 ----
function dismissToast(id) {
  toasts.value = toasts.value.filter((t) => t.id !== id)
}
function flash(type, text) {
  const id = ++toastSeq
  toasts.value.push({ id, type, text })
  // 错误停留久一点, 其余自动消失
  setTimeout(() => dismissToast(id), type === 'error' ? 6000 : 3500)
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const c = await getTradeConnectivity()
    conn.value = c.data
  } catch (e) {
    error.value = e.message; loading.value = false; return
  }
  const jobs = [
    getTradeStatus().then((s) => { status.value = s.data }).catch(() => {}),
    loadTrades(),
  ]
  if (connected.value) jobs.push(loadAccount(), loadOpenOrders())
  await Promise.allSettled(jobs)
  loading.value = false
}

// silent=true 用于后台轮询, 不弹 toast、失败时保留旧值避免闪烁
async function loadAccount(silent = false) {
  try {
    const r = await getTradeAccount()
    if (r.data?.ok) balances.value = r.data.balances || []
    else if (!silent && r.data?.error) flash('error', `余额: ${r.data.error}`)
  } catch (e) { if (!silent) flash('error', `余额加载失败: ${e.message}`) }
}

async function loadOpenOrders(silent = false) {
  try {
    const r = await getOpenOrders()
    if (r.data?.ok) openOrders.value = r.data.orders || []
    else if (!silent && r.data?.error) flash('error', `委托: ${r.data.error}`)
  } catch (e) { if (!silent) flash('error', `委托加载失败: ${e.message}`) }
}

async function loadTrades() {
  try {
    const t = await listTrades('simulation', 50)
    localTrades.value = t.data.trades
    tradesError.value = ''
  } catch (e) { tradesError.value = e.message }
}

// 后台轮询: 页面可见且已连接时, 每 5s 刷新委托/余额/记录
let pollTimer = null
let polling = false
async function refreshDynamic() {
  if (polling || document.hidden || !connected.value) return
  polling = true
  try { await Promise.allSettled([loadOpenOrders(true), loadAccount(true), loadTrades()]) }
  finally { polling = false }
}

async function submitOrder() {
  const sym = activeSymbol()
  if (!sym || !form.quantity) return flash('error', '请填写币种和数量')
  if (form.type === 'LIMIT' && !form.price) return flash('error', 'LIMIT 单需要填写价格')
  // 提前拦余额不足 (卖出量 > 持有, 常因上次买入被手续费吃掉零头)
  if (form.side === 'SELL' && Number(form.quantity) > availFree.value + 1e-12) {
    return flash('error', `${baseAsset.value} 不足: 可用 ${fmt(availFree.value, 6)}, 想卖 ${form.quantity}（点「全部」按可用量卖出）`)
  }
  if (form.side === 'BUY' && form.type === 'LIMIT' && estCost.value > availFree.value + 1e-9) {
    return flash('error', `USDT 不足: 可用 ${fmt(availFree.value, 2)}, 本单约需 ${fmt(estCost.value, 2)}`)
  }
  submitting.value = true
  try {
    const payload = {
      symbol: sym, side: form.side, type: form.type,
      quantity: form.quantity, time_in_force: form.time_in_force,
      price: form.type === 'MARKET' ? null : form.price,
    }
    const r = await placeOrder(payload)
    if (r.data?.ok) {
      const o = r.data.order
      flash('success', `下单成功: ${sym} #${o.orderId} ${o.status || ''}`)
      pct.value = 0
      await Promise.allSettled([loadOpenOrders(), loadAccount(), loadTrades()])
    } else {
      flash('error', r.data?.error || '下单失败')
    }
  } catch (e) { flash('error', e.message) } finally { submitting.value = false }
}

async function doCancel(o) {
  try {
    const r = await cancelOrder(o.symbol, o.orderId)
    if (r.data?.ok) {
      flash('success', `已撤单 #${o.orderId}`)
      await Promise.allSettled([loadOpenOrders(), loadAccount(), loadTrades()])
    } else { flash('error', r.data?.error || '撤单失败') }
  } catch (e) { flash('error', e.message) }
}

function fmt(n, d = 4) { const v = Number(n); return Number.isFinite(v) ? v.toFixed(d) : '-' }
function ts(ms) { return ms ? new Date(Number(ms)).toLocaleString('zh-CN', { hour12: false }) : '-' }

onMounted(async () => {
  try {
    const r = await listSymbols(false)
    symbols.value = r.data?.symbols || []
  } catch {}
  await nextTick()
  initChart()
  watchPrice(form.symbol)
  loadSymbolFilters(form.symbol)
  await loadAll()
  pollTimer = setInterval(refreshDynamic, 5000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  try { datafeed?.unsubscribe() } catch {}
  try { priceUnsub?.() } catch {}
  if (chartEl.value) chartEl.value.innerHTML = ''
  chart = null
})
</script>

<template>
  <div class="trade-page">
    <!-- 连通性状态条 -->
    <div class="card status-bar">
      <div class="status-left">
        <span class="dot" :class="connected ? 'on' : (conn.reachable ? 'warn' : 'off')"></span>
        <div>
          <div class="title">模拟盘 (Binance Demo Mode)</div>
          <div class="sub">
            <template v-if="connected">已连接沙盒账户 · Key {{ conn.api_key_masked }} · {{ conn.base_url }}</template>
            <template v-else-if="!configured">未配置凭据 — 设置 <code>BINANCE_DEMO_API_KEY</code> / <code>BINANCE_DEMO_API_SECRET</code> 后重启后端</template>
            <template v-else-if="conn.reachable">凭据无效: {{ conn.error }}</template>
            <template v-else>无法连接 demo 端点: {{ conn.error }}</template>
          </div>
        </div>
      </div>
      <button class="btn ghost" @click="loadAll" :disabled="loading">刷新</button>
    </div>


    <!-- 交易终端: 图表 + 下单面板 -->
    <div class="terminal">
      <div class="card chart-card">
        <div ref="chartEl" class="chart"></div>
      </div>

      <div class="card order-panel">
        <div class="op-row">
          <label class="grow">币种
            <select :value="form.symbol" @change="changeSymbol($event.target.value)">
              <option v-for="s in symbols" :key="s.symbol" :value="s.symbol">
                {{ s.symbol }} · {{ s.name_zh }}
              </option>
            </select>
          </label>
        </div>

        <div class="side-toggle">
          <button :class="{ active: form.side === 'BUY', buy: true }" @click="form.side = 'BUY'">买入</button>
          <button :class="{ active: form.side === 'SELL', sell: true }" @click="form.side = 'SELL'">卖出</button>
        </div>

        <fieldset :disabled="!connected" class="op-form">
          <label>类型
            <select v-model="form.type">
              <option value="LIMIT">限价 LIMIT</option>
              <option value="MARKET">市价 MARKET</option>
            </select>
          </label>
          <label v-if="form.type === 'LIMIT'">
            <span class="lbl-row">
              价格 (USDT)
              <button type="button" class="max-btn" @click="useMarketPrice"
                      :title="lastPrice ? '现价 ' + fmt(lastPrice, 2) : '等待行情'">
                市价 {{ lastPrice ? fmt(lastPrice, 2) : '…' }}
              </button>
            </span>
            <input v-model.number="form.price" type="number" step="any" placeholder="0.00" />
          </label>
          <label>
            <span class="lbl-row">
              数量 ({{ baseAsset }})
              <button v-if="form.side === 'SELL'" type="button" class="max-btn" @click="fillMax">全部</button>
            </span>
            <input v-model.number="form.quantity" type="number" step="any" />
          </label>
          <div class="avail">
            <span>可用 <b>{{ fmt(availFree, 6) }}</b> {{ availAsset }}</span>
            <span v-if="form.side === 'BUY' && estCost">约需 {{ fmt(estCost, 2) }} USDT</span>
          </div>

          <!-- 比例滑块: 按可用资金/持仓的百分比下单 -->
          <div class="pct-sizer">
            <input type="range" min="0" max="100" step="1" :value="pct"
                   @input="applyPct(+$event.target.value)" class="pct-slider"
                   :class="form.side === 'SELL' ? 'sell' : 'buy'" />
            <div class="pct-quick">
              <button v-for="p in [25, 50, 75, 100]" :key="p" type="button"
                      :class="{ active: pct === p }" @click="applyPct(p)">{{ p }}%</button>
            </div>
          </div>

          <button class="btn submit" :class="form.side === 'SELL' ? 'sell' : 'buy'"
                  @click="submitOrder" :disabled="submitting">
            {{ submitting ? '提交中...' : (form.side === 'BUY' ? '买入' : '卖出') }} {{ form.symbol.replace('USDT', '') }}
          </button>
        </fieldset>
        <p v-if="!connected" class="hint">连接沙盒账户后可下单</p>

        <div class="balances">
          <div class="bal-title">账户余额</div>
          <div v-if="!balances.length" class="bal-empty">— 无非零余额 —</div>
          <div v-for="b in balances" :key="b.asset" class="bal-row">
            <span class="asset">{{ b.asset }}</span>
            <span class="amt">{{ fmt(b.free, 4) }}</span>
            <span class="locked" v-if="b.locked">锁 {{ fmt(b.locked, 4) }}</span>
          </div>
        </div>
      </div>
    </div>

    <StateView :loading="loading" :error="error" />

    <!-- 当前委托 + 本地记录 并排一行 -->
    <div class="tables-row">
      <div class="card">
        <h3>当前委托 ({{ openOrders.length }})</h3>
        <StateView :empty="!openOrders.length" empty-text="无挂单" empty-icon="📋" />
        <div v-if="openOrders.length" class="table-scroll">
          <table>
            <thead><tr>
              <th>时间</th><th>币种</th><th>方向</th><th>类型</th>
              <th>价格</th><th>数量</th><th>已成交</th><th>状态</th><th></th>
            </tr></thead>
            <tbody>
              <tr v-for="o in openOrders" :key="o.orderId">
                <td>{{ ts(o.time) }}</td>
                <td class="sym-cell">{{ o.symbol }}</td>
                <td :class="o.side === 'BUY' ? 'pos' : 'neg'">{{ o.side }}</td>
                <td>{{ o.type }}</td>
                <td>{{ fmt(o.price) }}</td>
                <td>{{ fmt(o.origQty) }}</td>
                <td>{{ fmt(o.executedQty) }}</td>
                <td>{{ o.status }}</td>
                <td><button class="btn ghost sm" @click="doCancel(o)">撤单</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h3>本地交易记录 (最近 50 条)</h3>
        <div v-if="tradesError" class="card-err">
          加载失败: {{ tradesError }}
          <span v-if="tradesError.includes('500')"> —— 多为后端未重启 (修复在 models.py), 请重启后端</span>
        </div>
        <StateView v-else :empty="!localTrades.length" empty-text="暂无记录" empty-icon="📒" />
        <div v-if="localTrades.length" class="table-scroll">
          <table>
            <thead><tr><th>时间</th><th>币种</th><th>方向</th><th>价格</th><th>数量</th><th>备注</th></tr></thead>
            <tbody>
              <tr v-for="t in localTrades" :key="t.id">
                <td>{{ t.created_at }}</td>
                <td class="sym-cell">{{ t.symbol }}</td>
                <td :class="t.side === 'buy' ? 'pos' : 'neg'">{{ t.side === 'buy' ? '买入' : '卖出' }}</td>
                <td>{{ fmt(t.price) }}</td>
                <td>{{ fmt(t.amount) }}</td>
                <td class="note">{{ t.note }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 左下角气泡通知 -->
    <transition-group name="toast" tag="div" class="toast-wrap">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type" @click="dismissToast(t.id)">
        <span class="toast-ico">{{ t.type === 'success' ? '✓' : '!' }}</span>
        <span>{{ t.text }}</span>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.trade-page { display: flex; flex-direction: column; gap: 16px; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 20px;
}
.card h3 { font-size: 15px; margin-bottom: 12px; }

/* 状态条 */
.status-bar { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; }
.status-left { display: flex; align-items: center; gap: 14px; }
.status-bar .title { font-weight: 600; }
.status-bar .sub { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.status-bar code { background: var(--bg); padding: 1px 5px; border-radius: 4px; font-size: 11px; color: var(--yellow); }
.dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.dot.on { background: var(--green); box-shadow: 0 0 8px var(--green); }
.dot.warn { background: var(--yellow); }
.dot.off { background: var(--red); }

/* 左下角气泡通知 */
.toast-wrap {
  position: fixed; left: 20px; bottom: 20px; z-index: 9999;
  display: flex; flex-direction: column-reverse; gap: 10px;
  pointer-events: none;
}
.toast {
  pointer-events: auto; cursor: pointer;
  display: flex; align-items: center; gap: 10px;
  max-width: 360px; padding: 11px 14px; border-radius: 10px;
  font-size: 13px; line-height: 1.4;
  background: var(--bg-card); border: 1px solid var(--border);
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.toast-ico {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%;
  display: grid; place-items: center; font-size: 12px; font-weight: 700; color: #08130c;
}
.toast.success { border-color: var(--green); }
.toast.success .toast-ico { background: var(--green); }
.toast.error { border-color: var(--red); }
.toast.error .toast-ico { background: var(--red); color: #1a0608; }
/* 进出动画: 从左侧滑入, 淡出 */
.toast-enter-active, .toast-leave-active { transition: all 0.3s ease; }
.toast-enter-from { opacity: 0; transform: translateX(-20px); }
.toast-leave-to { opacity: 0; transform: translateX(-20px); }
.toast-leave-active { position: absolute; }

/* 终端布局: 图表 + 下单面板 */
.terminal { display: grid; grid-template-columns: 1fr 300px; gap: 16px; align-items: stretch; }
.chart-card { padding: 0; overflow: hidden; }
.chart { width: 100%; height: 520px; }

/* 下单面板 */
.order-panel { display: flex; flex-direction: column; gap: 14px; }
.op-row { display: flex; gap: 10px; }
.op-row .grow { flex: 1; }
.order-panel label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary); }
.order-panel select, .order-panel input {
  background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px 10px; color: var(--text); font-size: 13px; font-family: 'Consolas', monospace;
}
.side-toggle { display: flex; gap: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.side-toggle button {
  flex: 1; padding: 9px 0; background: var(--bg); color: var(--text-secondary);
  border: none; cursor: pointer; font-size: 14px; font-weight: 600;
}
.side-toggle button.buy.active { background: var(--green); color: #08130c; }
.side-toggle button.sell.active { background: var(--red); color: #1a0608; }
.op-form { border: none; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.op-form:disabled { opacity: 0.5; }
.lbl-row { display: flex; justify-content: space-between; align-items: center; }
.max-btn { background: transparent; border: 1px solid var(--border); color: var(--yellow); border-radius: 4px; padding: 1px 8px; font-size: 11px; cursor: pointer; }
.max-btn:hover { border-color: var(--yellow); }
.avail { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-secondary); margin-top: -4px; }
.avail b { color: var(--text); font-family: 'Consolas', monospace; }

/* 比例滑块 */
.pct-sizer { display: flex; flex-direction: column; gap: 8px; }
.pct-slider { -webkit-appearance: none; appearance: none; width: 100%; height: 4px; border-radius: 3px; background: var(--border); outline: none; cursor: pointer; }
.pct-slider::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 14px; height: 14px; border-radius: 50%; cursor: pointer; }
.pct-slider.buy::-webkit-slider-thumb { background: var(--green); }
.pct-slider.sell::-webkit-slider-thumb { background: var(--red); }
.pct-slider::-moz-range-thumb { width: 14px; height: 14px; border: none; border-radius: 50%; cursor: pointer; }
.pct-slider.buy::-moz-range-thumb { background: var(--green); }
.pct-slider.sell::-moz-range-thumb { background: var(--red); }
.pct-quick { display: flex; gap: 6px; }
.pct-quick button { flex: 1; padding: 5px 0; background: var(--bg); border: 1px solid var(--border); color: var(--text-secondary); border-radius: 5px; font-size: 11px; cursor: pointer; }
.pct-quick button:hover { border-color: var(--text-secondary); }
.pct-quick button.active { border-color: var(--yellow); color: var(--yellow); }
.btn {
  background: var(--bg); border: 1px solid var(--border); color: var(--text);
  padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;
}
.btn:hover { border-color: var(--text-secondary); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.sm { padding: 4px 10px; font-size: 12px; }
.btn.ghost { background: transparent; }
.btn.submit { padding: 11px 0; font-weight: 700; font-size: 14px; border: none; }
.btn.submit.buy { background: var(--green); color: #08130c; }
.btn.submit.sell { background: var(--red); color: #1a0608; }
.hint { font-size: 12px; color: var(--text-muted); }

/* 余额 */
.balances { border-top: 1px solid var(--border); padding-top: 12px; }
.bal-title { font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; }
.bal-empty { font-size: 12px; color: var(--text-muted); }
.bal-row { display: flex; align-items: baseline; gap: 8px; padding: 4px 0; font-family: 'Consolas', monospace; font-size: 13px; }
.bal-row .asset { color: var(--yellow); font-weight: 600; width: 64px; }
.bal-row .amt { flex: 1; text-align: right; }
.bal-row .locked { font-size: 11px; color: var(--text-muted); }

/* 表格 */
table { width: 100%; border-collapse: collapse; margin-top: 8px; }
th { text-align: left; padding: 9px 12px; background: var(--bg); color: var(--text-secondary); font-size: 11px; font-weight: 500; border-bottom: 1px solid var(--border); }
td { padding: 9px 12px; border-bottom: 1px solid var(--border); font-size: 13px; font-family: 'Consolas', monospace; }
.sym-cell { font-weight: 600; color: var(--yellow); }
.note { font-family: inherit; color: var(--text-secondary); font-size: 12px; }
.pos { color: var(--green); }
.neg { color: var(--red); }

/* 当前委托 + 本地记录 并排 */
.tables-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
.table-scroll { overflow-x: auto; }
.card-err { padding: 14px; border-radius: 8px; font-size: 12px; background: rgba(246,70,93,0.1); border: 1px solid var(--red); color: var(--red); }
:deep(.empty-state) { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 28px; color: var(--text-secondary); }
:deep(.empty-state .icon) { font-size: 28px; }

@media (max-width: 980px) {
  .terminal { grid-template-columns: 1fr; }
  .tables-row { grid-template-columns: 1fr; }
}
</style>
