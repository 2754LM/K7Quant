<script setup>
import { ref, onMounted, computed, nextTick, inject } from 'vue'
import {
  getStrategies, getStrategyTemplates, validateStrategyCode,
  createStrategy, deleteStrategy, updateStrategy, getDslDocs,
  compilePython,
} from '../api'

import StrategyPicker from '../components/StrategyPicker.vue'
import StateView from '../components/StateView.vue'

const cfg = inject('cfg')
const reloadCfg = inject('reload')

const strategies = ref([])
const templates = ref({ builtin: [], blank_template: '' })
const selectedId = ref(null)
const editForm = ref({ name: '', description: '', category: 'custom', code: '', code_type: 'dsl', params_schema: {}, context_timeframes: [], context_lookback: 20 })

// 可选的 timeframe 列表 (跟系统保持一致)
const TIMEFRAME_OPTIONS = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '1w']

// 上下文变量名预览 (DSL 模式)
const ctxVarPreview = computed(() => {
  if (!editForm.value.context_timeframes?.length) return []
  const cols = ['close', 'open', 'high', 'low', 'volume']
  const stats = ['ma', 'max', 'min', 'std', 'sum']
  const n = editForm.value.context_lookback || 20
  const out = []
  for (const tf of editForm.value.context_timeframes) {
    const tfn = tf.replace('/', '_')
    for (const c of cols) out.push(`ctx_${tfn}_${c}`)
    for (const s of stats) out.push(`ctx_${tfn}_${s}${n}`)
  }
  return out
})

function toggleContextTf(tf) {
  const list = editForm.value.context_timeframes || []
  if (list.includes(tf)) {
    editForm.value.context_timeframes = list.filter(t => t !== tf)
  } else {
    editForm.value.context_timeframes = [...list, tf]
  }
  validate()
}
const isNew = ref(false)
const loading = ref(false)
const error = ref('')
const msg = ref('')
const validation = ref(null)
const dslDocs = ref({ overview: '', structure: [], columns: [], operators: [], functions: [], examples: [], tips: [] })
const dslTabs = [
  { key: 'overview', label: '总览' },
  { key: 'columns', label: '数据列' },
  { key: 'operators', label: '操作符' },
  { key: 'functions', label: '函数库' },
  { key: 'examples', label: '示例' },
  { key: 'tips', label: '技巧' },
  { key: 'python', label: '🐍 Python 沙箱' },
]
const dslTab = ref('overview')
const funcCatFilter = ref('全部')
const functionCategories = computed(() => {
  const cats = ['全部']
  if (dslDocs.value?.functions) cats.push(...dslDocs.value.functions.map(c => c.cat))
  return cats
})
let validationTimer = null

// Python 沙箱 quick-ref (点击插入到光标)
const pythonSnippets = {
  init: `def init():
    return {
        "entry": 0,
        "qty": 0,
    }`,
  on_bar: `def on_bar(state):
    p = ctx.now()
    if state["entry"] == 0:
        state["entry"] = p
        buy(100)
        return`,
  ctx_now: 'p = ctx.now()  # 当前 close',
  ctx_ohlc: 'o, h, l, c = ctx.ohlc()  # 需要在 _Context 加',
  ctx_df: 'ctx.df  # 完整 DataFrame (open/high/low/close/volume/amount/time)',
  ctx_close: 'ctx.close  # 收盘价 Series (截至当前 bar)',
  ctx_MA: 'ma7 = ctx.MA(7)  # 简单均线, 同 DSL 因子',
  ctx_RSI: 'rsi14 = ctx.RSI(14)',
  ctx_MACD: 'macd, sig, hist = ctx.MACD()  # 3 元组',
  ctx_BOLL: 'upper, mid, lower = ctx.BOLL(20, 2.0)',
  ctx_cross: 'ctx.cross_up(ma7, ma25)  # bool Series',
  ctx_ref: 'ctx.ref(series, 1)  # 上一根的值',
  ctx_bars: 'ctx.bars()  # 当前是第几根 (0-indexed)',
  buy: 'buy(100)  # 买 100 USDT',
  sell: 'sell(0.001)  # 卖 0.001 BTC',
  sell_all: 'sell_all()  # 全平',
  cash: 'cash()  # 当前现金',
  equity: 'equity()  # 当前总权益',
  position: 'position()  # 持仓 dict {qty, avg, value}',
  np: 'np.array([1, 2, 3])  # numpy',
  pd: 'pd.DataFrame({"a": [1, 2]})  # pandas',
  ctx_klines: 'df = ctx.klines("15m", n=20)  # 拉取 15m 最近 20 根 (按需缓存)',
  ctx_series: 's = ctx.series("1h", "close", n=50)  # 拿 1h close Series',
  ctx_factor: 'rsi_15m = ctx.factor("RSI", "15m", n=20)  # 在 15m 上跑 RSI',
  ctx_now_tf: 'last_15m = ctx.now_tf("15m")  # 最新 15m close (单值)',
  ctx_ref_tf: 'prev_15m = ctx.ref_tf("15m", "close", 1)  # 上一根 15m close',
}

const selectedStrategy = computed(() => strategies.value.find(s => s.id === selectedId.value))

async function load() {
  loading.value = true
  try {
    const res = await getStrategies()
    strategies.value = res.data.strategies
    const tres = await getStrategyTemplates()
    templates.value = tres.data
    if (res.data.strategies.length && !selectedId.value) {
      selectStrategy(res.data.strategies[0].id)
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function selectStrategy(id) {
  selectedId.value = id
  const s = strategies.value.find(x => x.id === id)
  if (s) {
    editForm.value = {
      name: s.name, description: s.description, category: s.category,
      code: s.code, code_type: s.code_type || 'dsl',
      params_schema: s.params_schema,
      context_timeframes: s.context_timeframes || [],
      context_lookback: s.context_lookback || 20,
    }
    isNew.value = false
    validate()
  }
}

function newStrategy() {
  selectedId.value = null
  isNew.value = true
  editForm.value = {
    name: '新策略',
    description: '',
    category: 'custom',
    code_type: 'dsl',
    code: templates.value.blank_template || 'signal = MA(close, 7) > MA(close, 25)\n止损 = 0.05\n止盈 = 0.10\n仓位 = 1.0',
    params_schema: {},
    context_timeframes: [],
    context_lookback: 20,
  }
  validate()
}

function useTemplate(t) {
  selectedId.value = null
  isNew.value = true
  editForm.value = {
    name: t.name,
    description: t.description,
    category: t.category,
    code: t.code,
    code_type: t.code_type || 'dsl',
    params_schema: t.params_schema,
    context_timeframes: t.context_timeframes || [],
    context_lookback: t.context_lookback || 20,
  }
  validate()
}

function switchCodeType(type) {
  if (editForm.value.code_type === type) return
  if (type === 'python' && !editForm.value.code.includes('def on_bar')) {
    // 切到 Python 但当前代码不像 Python, 给个默认模板
    if (!confirm('切到 Python 模式会替换当前代码为默认 Python 模板, 继续?')) return
    editForm.value.code = `# Python 策略: 自定义 on_bar + buy/sell
# 跌 1% 翻倍加仓, 涨 0.5% 全平

def init():
    return {"entry": 0, "qty": 0, "base": 100, "grids": 0}

def on_bar(state):
    p = ctx.now()
    if p <= 0:
        return
    if state["entry"] == 0:
        state["entry"] = p
        state["qty"] = state["base"]
        buy(state["qty"])
        return
    if p < state["entry"] * 0.99 and state["grids"] < 5:
        state["entry"] = p
        state["qty"] *= 2
        state["grids"] += 1
        buy(state["qty"])
        return
    if p > state["entry"] * 1.005:
        sell_all()
        state["entry"] = 0
        state["qty"] = state["base"]
        state["grids"] = 0
`
  }
  editForm.value.code_type = type
  validate()
}

function validate() {
  if (validationTimer) clearTimeout(validationTimer)
  validationTimer = setTimeout(async () => {
    try {
      const res = await validateStrategyCode(
        editForm.value.code,
        editForm.value.code_type,
        editForm.value.context_timeframes || [],
        editForm.value.context_lookback || 20,
      )
      validation.value = res.data
    } catch (e) {
      validation.value = { ok: false, error: e.message }
    }
  }, 500)
}

function insertSnippet(snippet) {
  const ta = document.querySelector('.code-area')
  if (!ta) {
    editForm.value.code += '\n' + snippet
    validate()
    return
  }
  const start = ta.selectionStart || 0
  const end = ta.selectionEnd || 0
  const before = editForm.value.code.slice(0, start)
  const after = editForm.value.code.slice(end)
  editForm.value.code = before + '\n' + snippet + '\n' + after
  validate()
  nextTick(() => {
    ta.focus()
    const pos = before.length + snippet.length + 2
    ta.setSelectionRange(pos, pos)
  })
}

async function save() {
  loading.value = true
  msg.value = ''
  try {
    if (isNew.value) {
      const res = await createStrategy(editForm.value)
      msg.value = '✓ 已创建'
      isNew.value = false
      await load()
      selectStrategy(res.data.id)
    } else {
      await updateStrategy(selectedId.value, editForm.value)
      msg.value = '✓ 已保存'
      await load()
    }
    if (reloadCfg) await reloadCfg()
  } catch (e) {
    msg.value = '✗ ' + e.message
  } finally {
    loading.value = false
  }
}

async function del() {
  if (!selectedId.value || isNew.value) return
  if (!confirm('确认删除这个策略?')) return
  try {
    await deleteStrategy(selectedId.value)
    selectedId.value = null
    isNew.value = true
    await load()
  } catch (e) {
    msg.value = '✗ ' + e.message
  }
}

function copyExample(code) {
  navigator.clipboard?.writeText(code).then(
    () => { msg.value = '✓ 已复制到剪贴板' },
    () => { msg.value = '✗ 复制失败' }
  )
}
function applyExample(ex) {
  selectedId.value = null
  isNew.value = true
  editForm.value = {
    name: ex.name,
    description: `${ex.name} 示例策略`,
    category: 'custom',
    code: ex.code,
    params_schema: {},
  }
  validate()
  msg.value = `✓ 已加载「${ex.name}」模板`
}

onMounted(async () => {
  await load()
  // 原来用原生 fetch().data (拿不到数据), 改用已封装的 axios getDslDocs()
  try {
    dslDocs.value = (await getDslDocs()).data
  } catch (e) {
    console.error('dsl-docs', e)
  }
})
</script>

<template>
  <div class="strategy-editor">
    <div class="sidebar card">
      <div class="sidebar-header">
        <h3>策略库</h3>
        <button class="btn-primary" @click="newStrategy">+ 新建</button>
      </div>
      <div class="strategy-list">
        <div v-for="s in strategies" :key="s.id"
          :class="['strategy-item', { active: s.id === selectedId, builtin: s.is_builtin, python: s.code_type === 'python' }]"
          @click="selectStrategy(s.id)">
          <div class="name">
            {{ s.name }}
            <span v-if="s.is_builtin" class="badge-sm">预置</span>
            <span v-if="s.code_type === 'python'" class="badge-sm py">PY</span>
          </div>
          <div class="desc">{{ s.description }}</div>
        </div>
      </div>

      <h4 style="margin-top: 20px; font-size: 13px; color: var(--text-secondary)">从模板开始</h4>
      <div class="template-list">
        <div v-for="t in templates.builtin" :key="t.name" class="template-item" @click="useTemplate(t)">
          <strong>{{ t.name }}</strong>
          <small>{{ t.description }}</small>
        </div>
      </div>
    </div>

    <div class="editor-area">
      <div class="card">
        <div class="form-row">
          <div class="form-group grow">
            <label>名称 <span class="hint-required">*</span></label>
            <input type="text" v-model="editForm.name" @input="validate" placeholder="给策略起个名字" />
            <span class="param-hint">命名建议: <code>技术 + 方向 + 周期</code>, 例如 <code>双均线趋势-4h</code> / <code>RSI反转-1h</code> / <code>量价齐升-1d</code></span>
          </div>
          <div class="form-group">
            <label>分类</label>
            <select v-model="editForm.category">
              <option value="trend">趋势 (trend)</option>
              <option value="mean_reversion">均值回归 (mean_reversion)</option>
              <option value="momentum">动量 (momentum)</option>
              <option value="breakout">突破 (breakout)</option>
              <option value="volume">成交量 (volume)</option>
              <option value="custom">自定义 (custom)</option>
            </select>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group grow">
            <label>说明 <span class="hint-muted">(选填, 用于快速回忆这个策略做什么)</span></label>
            <input type="text" v-model="editForm.description" @input="validate"
              placeholder="一句话讲清楚: 何时买入, 何时卖出, 适用什么行情" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>代码类型</label>
            <div class="code-type-tabs">
              <button type="button" :class="{ active: editForm.code_type === 'dsl' }"
                @click="switchCodeType('dsl')">DSL 单行表达式</button>
              <button type="button" :class="{ active: editForm.code_type === 'python' }"
                @click="switchCodeType('python')">🐍 Python 脚本</button>
            </div>
            <span class="param-hint">
              <span v-if="editForm.code_type === 'dsl'">单行表达式, 适合大多数技术指标策略</span>
              <span v-else>完整 Python, 可有状态/循环/加仓, 自带 33+ 因子</span>
            </span>
          </div>
          <div class="form-group">
            <label>分类</label>
            <select v-model="editForm.category">
              <option value="trend">趋势 (trend)</option>
              <option value="mean_reversion">均值回归 (mean_reversion)</option>
              <option value="momentum">动量 (momentum)</option>
              <option value="breakout">突破 (breakout)</option>
              <option value="volume">成交量 (volume)</option>
              <option value="martingale">Martingale (martingale)</option>
              <option value="custom">自定义 (custom)</option>
            </select>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group grow">
            <label>
              策略代码
              <span class="hint-muted">
                ({{ editForm.code_type === 'python' ? 'Python: def init() + def on_bar(state)' : 'DSL: signal = 表达式' }})
              </span>
            </label>
            <textarea v-model="editForm.code" @input="validate" rows="20"
              class="code-area" spellcheck="false"></textarea>
            <div class="hint" v-if="editForm.code_type === 'dsl'">
              signal = 表达式 (必需) | 止损/止盈/仓位/频率 (可选)
            </div>
            <div class="hint" v-else>
              必填 def on_bar(state); 可选 def init() 返回 state dict; 必填函数: buy/sell/sell_all/cash/equity/position
            </div>
          </div>
          <div class="form-group python-snippets" v-if="editForm.code_type === 'python'">
            <label>快速插入</label>
            <div class="snippet-grid">
              <button type="button" v-for="(code, key) in pythonSnippets" :key="key"
                class="snippet-btn" @click="insertSnippet(code)">{{ key }}</button>
            </div>
            <span class="param-hint">点击按钮插入示例代码到光标位置</span>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group grow">
            <label>
              🕐 运行周期 (多 timeframe 上下文)
              <span class="hint-muted">(除主图外, 额外加载的时间框架, 用于跨周期策略)</span>
            </label>
            <div class="ctx-config">
              <div class="ctx-tfs">
                <span class="ctx-label">时间框架:</span>
                <button v-for="tf in TIMEFRAME_OPTIONS" :key="tf" type="button"
                  :class="['ctx-tf-btn', { active: (editForm.context_timeframes || []).includes(tf) }]"
                  @click="toggleContextTf(tf)">
                  {{ tf }}
                </button>
              </div>
              <div class="ctx-lookback">
                <span class="ctx-label">回看根数:</span>
                <input type="number" v-model.number="editForm.context_lookback" @input="validate"
                  min="2" max="500" class="ctx-num" />
                <span class="ctx-hint">每个 context tf 拉最近多少根 K 线 (用于算 ma/max/min/std/sum)</span>
              </div>
              <div v-if="ctxVarPreview.length" class="ctx-preview">
                <span class="ctx-label">可用变量:</span>
                <code v-for="v in ctxVarPreview.slice(0, 8)" :key="v">{{ v }}</code>
                <code v-if="ctxVarPreview.length > 8" class="more">+{{ ctxVarPreview.length - 8 }}...</code>
                <span class="ctx-hint">{{ editForm.code_type === 'dsl' ? 'DSL 表达式里直接用, 也可喂给 MA/RSI 等因子' : 'Python: ctx.klines("15m", n=20) / ctx.factor("RSI", "15m", n=20)' }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="validation" v-if="validation">
          <span v-if="validation.ok" class="ok">
            ✓ {{ editForm.code_type === 'python'
                ? 'Python 编译通过' + (validation.has_init ? ' (含 init)' : '')
                : '语法正确' }}
          </span>
          <span v-else class="err">✗ {{ validation.error }}</span>
        </div>
        <div class="actions">
          <button class="btn-primary" @click="save" :disabled="loading">
            {{ isNew ? '创建' : '保存' }}
          </button>
          <button v-if="!isNew && selectedStrategy && !selectedStrategy.is_builtin"
            class="btn-danger" @click="del">删除</button>
          <span v-if="msg" class="msg">{{ msg }}</span>
        </div>
      </div>

      <div class="card dsl-docs-card">
        <div class="docs-header">
          <h3>📖 DSL 语法手册</h3>
          <div class="docs-tabs">
            <button v-for="tab in dslTabs" :key="tab.key"
              :class="{ active: dslTab === tab.key }"
              @click="dslTab = tab.key">{{ tab.label }}</button>
          </div>
        </div>

        <!-- 总览 -->
        <div v-if="dslTab === 'overview'" class="docs-pane">
          <p class="overview">{{ dslDocs.overview }}</p>
          <h4>结构</h4>
          <div class="kv-table">
            <div v-for="item in dslDocs.structure" :key="item.syntax" class="kv-row">
              <code class="kv-syntax" :class="{ required: item.required }">{{ item.syntax }}</code>
              <span class="kv-desc">{{ item.desc }}<span v-if="item.required" class="req-mark">* 必需</span></span>
            </div>
          </div>
        </div>

        <!-- 数据列 -->
        <div v-if="dslTab === 'columns'" class="docs-pane">
          <p class="hint">表达式里直接写这些名字, 表示对应的 K 线数据列。</p>
          <table class="docs-table">
            <thead><tr><th>列名</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="c in dslDocs.columns" :key="c.name">
                <td><code>{{ c.name }}</code></td>
                <td>{{ c.desc }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 操作符 -->
        <div v-if="dslTab === 'operators'" class="docs-pane">
          <table class="docs-table">
            <thead><tr><th style="width: 30%">写法</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="op in dslDocs.operators" :key="op.op">
                <td><code>{{ op.op }}</code></td>
                <td>{{ op.desc }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 函数库 (按分类) -->
        <div v-if="dslTab === 'functions'" class="docs-pane">
          <div class="func-cat-filter">
            <button v-for="cat in functionCategories" :key="cat"
              :class="{ active: funcCatFilter === cat }"
              @click="funcCatFilter = cat">{{ cat }}</button>
          </div>
          <div v-for="cat in (funcCatFilter === '全部' ? dslDocs.functions : dslDocs.functions.filter(c => c.cat === funcCatFilter))"
               :key="cat.cat" class="func-cat">
            <h4 class="func-cat-title">{{ cat.cat }}</h4>
            <table class="docs-table">
              <thead><tr><th style="width: 30%">函数</th><th>签名</th><th>说明</th></tr></thead>
              <tbody>
                <tr v-for="f in cat.items" :key="f.id">
                  <td><strong class="fn-id">{{ f.id }}</strong></td>
                  <td><code class="fn-sig">{{ f.sig }}</code></td>
                  <td>{{ f.desc }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 示例 -->
        <div v-if="dslTab === 'examples'" class="docs-pane">
          <div v-for="ex in dslDocs.examples" :key="ex.name" class="example">
            <div class="ex-head">
              <strong>{{ ex.name }}</strong>
              <button class="ex-copy" @click="copyExample(ex.code)">复制</button>
              <button class="ex-apply" @click="applyExample(ex)">套用此模板</button>
            </div>
            <pre class="ex-code">{{ ex.code }}</pre>
          </div>
        </div>

        <!-- 技巧 -->
        <div v-if="dslTab === 'tips'" class="docs-pane">
          <ul class="tips-list">
            <li v-for="t in dslDocs.tips" :key="t" :class="{ good: t.startsWith('✓'), bad: t.startsWith('✗') }">{{ t }}</li>
          </ul>
        </div>

        <!-- 🐍 Python 沙箱 -->
        <div v-if="dslTab === 'python'" class="docs-pane">
          <p class="overview">
            Python 沙箱给最大自由度: 可以有状态、循环、动态仓位、自定义加仓逻辑。
            <br>代码每根 K 线调用 <code>def on_bar(state)</code>, 通过 <code>ctx</code> 拿数据, 通过 <code>buy/sell/sell_all</code> 下单。
          </p>

          <h4>📦 必填结构</h4>
          <pre class="ex-code">def init():
    """可选, 返回 state dict (跨 bar 持久化)"""
    return {"entry": 0, "qty": 0, "base": 100, "grids": 0}

def on_bar(state):
    """必填, 每根 K 线调用一次"""
    p = ctx.now()        # 当前 bar 收盘价
    if p &lt; state["entry"] * 0.99:
        buy(state["qty"] * 2)   # 翻倍加仓</pre>

          <h4>💹 交易 (直接调用, 不需要 return)</h4>
          <table class="docs-table">
            <thead><tr><th style="width: 30%">调用</th><th>说明</th></tr></thead>
            <tbody>
              <tr><td><code>buy(usdt)</code></td><td>买入 usdt 金额 (USDT计价, 不是币数)</td></tr>
              <tr><td><code>sell(coin_qty)</code></td><td>卖出 coin_qty 币数</td></tr>
              <tr><td><code>sell_all()</code></td><td>全平当前持仓</td></tr>
              <tr><td><code>cash()</code></td><td>当前可用现金 (USDT)</td></tr>
              <tr><td><code>equity()</code></td><td>当前总权益 = 现金 + 持仓价值</td></tr>
              <tr><td><code>position()</code></td><td>返回 <code>{qty, avg, value}</code> 持仓字典</td></tr>
            </tbody>
          </table>

          <h4>📊 ctx (数据上下文)</h4>
          <table class="docs-table">
            <thead><tr><th style="width: 40%">属性/方法</th><th>说明</th></tr></thead>
            <tbody>
              <tr><td><code>ctx.now()</code></td><td>当前 close (单值)</td></tr>
              <tr><td><code>ctx.open() / high() / low() / volume() / amount()</code></td><td>当前 bar 的开/高/低/量/额</td></tr>
              <tr><td><code>ctx.time()</code></td><td>当前 bar 时间字符串</td></tr>
              <tr><td><code>ctx.bars()</code></td><td>当前是第几根 (0-indexed)</td></tr>
              <tr><td><code>ctx.df</code></td><td>完整 DataFrame (open/high/low/close/volume/amount/time)</td></tr>
              <tr><td><code>ctx.close / ctx.high / ctx.low / ...</code></td><td>截至当前 bar 的 Series</td></tr>
              <tr><td><code>ctx.MA(n) / ctx.EMA(n) / ctx.RSI(n) / ctx.MACD() / ctx.BOLL(p, σ) / ...</code></td><td>33+ 因子, 同 DSL 调用方式</td></tr>
              <tr><td><code>ctx.cross_up(a, b) / ctx.cross_down(a, b)</code></td><td>交叉判断, 返回 bool Series</td></tr>
              <tr><td><code>ctx.ref(series, n)</code></td><td>引用 n 根前的值 (n=1 = 上一根)</td></tr>
              <tr><td><code>ctx.bars_since(cond)</code></td><td>上次条件为 True 距今多少根</td></tr>
              <tr><td><code>ctx.pct_change(n)</code></td><td>N 根涨幅</td></tr>
              <tr><td><code>ctx.std / sma / ema / sum(series=None, n)</code></td><td>滚动统计 (series 默认 ctx.close)</td></tr>
            </tbody>
          </table>

          <h4>🕐 ctx (多 timeframe 上下文)</h4>
          <p class="hint">设置运行周期后, 这些方法可用 (按需自动加载 K 线并缓存):</p>
          <table class="docs-table">
            <thead><tr><th style="width: 45%">方法</th><th>说明</th></tr></thead>
            <tbody>
              <tr><td><code>ctx.klines("15m", n=20)</code></td><td>截至当前 bar 时间的 15m K 线 DataFrame (最近 20 根)</td></tr>
              <tr><td><code>ctx.series("15m", "close", n=20)</code></td><td>同上, 只返回 close 列 Series</td></tr>
              <tr><td><code>ctx.now_tf("15m")</code></td><td>最近 1 根 15m 的 close (单值)</td></tr>
              <tr><td><code>ctx.ref_tf("15m", "close", n=1)</code></td><td>15m 倒数第 n 根的 close (n=1=上一根)</td></tr>
              <tr><td><code>ctx.factor("RSI", "15m", n=20)</code></td><td>在 15m 上下文上跑 RSI 因子, 返回 Series</td></tr>
            </tbody>
          </table>
          <p class="hint">示例: <code>c15 = ctx.klines("15m", n=20); rsi15 = ctx.factor("RSI", "15m", n=20)</code></p>

          <h4>🔧 沙箱 globals (预导入)</h4>
          <p class="hint">
            <code>pd</code> / <code>np</code> / <code>math</code> / <code>json</code> / <code>datetime</code> /
            <code>collections</code> / <code>itertools</code> / <code>functools</code> 全部直接可用。
            Python 内置也几乎全开 (除 open/exec/eval/getattr/setattr/import 等危险函数)。
          </p>

          <h4>🛡️ 安全机制</h4>
          <ul class="tips-list">
            <li class="bad">✗ 禁止 <code>import</code> / <code>from xxx import</code></li>
            <li class="bad">✗ 禁止 <code>open / exec / eval / getattr / setattr / delattr / __import__</code></li>
            <li class="bad">✗ 禁止 dunder 属性访问 (<code>__class__ / __globals__ / ...</code>)</li>
            <li class="bad">✗ 禁止 <code>async / await / global / nonlocal</code></li>
            <li class="good">✓ 单 bar 抛错自动跳过, 不中断回测</li>
            <li class="good">✓ 错误信息会写入 <code>state["_last_error"]</code> 便于调试</li>
          </ul>

          <h4>📝 完整示例: Martingale 网格</h4>
          <pre class="ex-code">def init():
    return {
        "entry": 0,           # 上次加仓价
        "qty": 0,             # 当前持仓 USDT 价值
        "base_qty": 100,      # 基础仓
        "grid_count": 0,      # 当前网格层数
        "max_grid": 5,        # 最大层数
    }

def on_bar(state):
    p = ctx.now()
    if p &lt;= 0:
        return
    # 首次建仓
    if state["entry"] == 0:
        state["entry"] = p
        state["qty"] = state["base_qty"]
        buy(state["qty"])
        return
    # 跌 1% 翻倍加仓 (限制层数)
    if p &lt; state["entry"] * 0.99 and state["grid_count"] &lt; state["max_grid"]:
        state["entry"] = p
        state["qty"] *= 2
        state["grid_count"] += 1
        buy(state["qty"])
        return
    # 涨 0.5% 全平 + 重置
    if p &gt; state["entry"] * 1.005:
        sell_all()
        state["entry"] = 0
        state["qty"] = state["base_qty"]
        state["grid_count"] = 0
        return</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.strategy-editor { display: grid; grid-template-columns: 320px 1fr; gap: 16px; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sidebar-header h3 { font-size: 16px; }
.strategy-list { display: flex; flex-direction: column; gap: 6px; max-height: 400px; overflow-y: auto; }
.strategy-item {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}
.strategy-item:hover { border-color: var(--yellow); }
.strategy-item.active { border-color: var(--yellow); background: rgba(240,185,11,0.08); }
.strategy-item.builtin { border-left: 3px solid var(--yellow); }
.name { font-weight: 600; font-size: 13px; display: flex; align-items: center; gap: 6px; }
.badge-sm {
  background: var(--yellow);
  color: #000;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}
.desc { font-size: 11px; color: var(--text-secondary); margin-top: 4px; line-height: 1.4; }
.template-list { display: flex; flex-direction: column; gap: 4px; }
.template-item {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.template-item:hover { border-color: var(--yellow); }
.template-item small { color: var(--text-secondary); display: block; margin-top: 2px; }

.editor-area { display: flex; flex-direction: column; gap: 16px; }
.form-row { display: flex; gap: 12px; margin-bottom: 16px; }
.form-group { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.form-group.grow { flex: 1; }
.form-group label { font-size: 12px; color: var(--text-secondary); }
.form-group input, .form-group select, .form-group textarea {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
.form-group textarea { width: 100%; resize: vertical; }
.form-group input:focus, .form-group select:focus, .form-group textarea:focus { border-color: var(--yellow); }
.form-group .hint { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.form-group .param-hint { font-size: 11px; color: var(--text-muted); margin-top: 4px; line-height: 1.4; }
.form-group .param-hint code {
  background: var(--bg-elevated);
  padding: 1px 5px;
  border-radius: 3px;
  color: var(--yellow);
  font-family: 'Consolas', monospace;
  font-size: 10px;
}
.hint-required { color: var(--red); margin-left: 2px; }
.hint-muted { color: var(--text-muted); font-weight: 400; font-size: 10px; }
.editor-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.code-area {
  width: 100%;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.5;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  color: var(--text);
  resize: vertical;
}
.code-area:focus { outline: none; border-color: var(--yellow); }
.validation { margin-bottom: 12px; font-size: 12px; }
.validation .ok { color: var(--green); }
.validation .err { color: var(--red); }
.actions { display: flex; gap: 8px; align-items: center; }
.msg { font-size: 13px; color: var(--text-secondary); }
.docs {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  white-space: pre-wrap;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 16px;
}

/* ============ DSL 文档区 ============ */
.docs-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.docs-header h3 { font-size: 16px; }
.docs-tabs { display: flex; gap: 4px; flex-wrap: wrap; }
.docs-tabs button {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 5px 12px;
  border-radius: 14px;
  font-size: 12px;
  cursor: pointer;
}
.docs-tabs button.active { background: var(--yellow); color: #000; border-color: var(--yellow); font-weight: 600; }
.docs-tabs button:hover:not(.active) { border-color: var(--yellow); }

.docs-pane { font-size: 13px; line-height: 1.6; }
.overview { color: var(--text-secondary); padding: 8px 12px; background: var(--bg); border-radius: 6px; }
.docs-pane h4 { margin: 12px 0 8px; font-size: 13px; color: var(--text-secondary); }

/* KV 表 (总览结构) */
.kv-table { display: flex; flex-direction: column; gap: 4px; }
.kv-row {
  display: grid; grid-template-columns: 240px 1fr; gap: 12px;
  padding: 6px 8px; border-radius: 4px;
}
.kv-row:hover { background: var(--bg); }
.kv-syntax {
  font-family: 'Consolas', monospace; font-size: 12px;
  color: var(--yellow); white-space: nowrap;
}
.kv-syntax.required::before { content: '⚡ '; color: var(--red); }
.kv-desc { font-size: 12px; color: var(--text-secondary); }
.req-mark { color: var(--red); font-size: 10px; margin-left: 4px; }

/* 通用表格 */
.docs-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.docs-table th {
  text-align: left; padding: 6px 10px;
  background: var(--bg); color: var(--text-secondary);
  font-weight: 500; border-bottom: 1px solid var(--border);
}
.docs-table td {
  padding: 6px 10px; border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.docs-table code {
  background: var(--bg-elevated); padding: 1px 6px; border-radius: 3px;
  color: var(--yellow); font-family: 'Consolas', monospace; font-size: 11px;
}
.fn-id { color: var(--yellow); }
.fn-sig { white-space: nowrap; }

/* 函数分类筛选 */
.func-cat-filter { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 10px; }
.func-cat-filter button {
  background: var(--bg); border: 1px solid var(--border); color: var(--text-secondary);
  padding: 3px 10px; border-radius: 12px; font-size: 11px; cursor: pointer;
}
.func-cat-filter button.active { background: var(--yellow); color: #000; border-color: var(--yellow); }
.func-cat { margin-top: 14px; }
.func-cat-title {
  font-size: 12px; color: var(--text-muted); margin-bottom: 4px;
  border-left: 3px solid var(--yellow); padding-left: 8px;
}

/* 示例 */
.example { margin-bottom: 14px; padding: 10px 12px; background: var(--bg); border-radius: 6px; }
.ex-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
}
.ex-head strong { font-size: 13px; flex: 1; }
.ex-copy, .ex-apply {
  background: var(--bg-card); border: 1px solid var(--border);
  color: var(--text-secondary); padding: 2px 10px; border-radius: 4px;
  font-size: 11px; cursor: pointer;
}
.ex-copy:hover, .ex-apply:hover { border-color: var(--yellow); color: var(--yellow); }
.ex-code {
  margin: 0; padding: 8px 12px;
  background: var(--bg-card); border-radius: 4px;
  font-size: 12px; color: var(--yellow);
  font-family: 'Consolas', monospace; white-space: pre-wrap;
  border: 1px solid var(--border);
}

/* 技巧 */
.tips-list { list-style: none; padding: 0; margin: 0; }
.tips-list li {
  padding: 6px 12px; margin-bottom: 4px; border-radius: 4px;
  background: var(--bg); font-size: 12px; line-height: 1.6;
}
.tips-list li.good { border-left: 3px solid var(--green); }
.tips-list li.bad { border-left: 3px solid var(--red); }

/* ============ 代码类型切换 ============ */
.code-type-tabs { display: flex; gap: 4px; }
.code-type-tabs button {
  flex: 1; background: var(--bg); border: 1px solid var(--border);
  color: var(--text-secondary); padding: 6px 12px; border-radius: 6px;
  font-size: 12px; cursor: pointer; transition: all 0.2s;
}
.code-type-tabs button.active {
  background: rgba(240,185,11,0.15); border-color: var(--yellow);
  color: var(--yellow); font-weight: 600;
}
.code-type-tabs button:hover:not(.active) { border-color: var(--yellow); }

/* ============ Python 标识 ============ */
.badge-sm.py {
  background: linear-gradient(135deg, #3776ab, #ffd43b);
  color: #000;
  font-size: 9px;
  font-weight: 700;
}
.strategy-item.python {
  border-left: 3px solid #3776ab;
}

/* ============ Python 快速插入 ============ */
.python-snippets { max-width: 220px; }
.snippet-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  max-height: 400px;
  overflow-y: auto;
}
.snippet-btn {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 5px 8px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  font-family: 'Consolas', monospace;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.snippet-btn:hover {
  background: rgba(240,185,11,0.1);
  border-color: var(--yellow);
  color: var(--yellow);
}

/* ============ 运行周期 (context timeframes) ============ */
.ctx-config {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ctx-tfs, .ctx-lookback, .ctx-preview {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.ctx-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
  min-width: 80px;
}
.ctx-tf-btn {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-family: 'Consolas', monospace;
  cursor: pointer;
  transition: all 0.15s;
}
.ctx-tf-btn:hover { border-color: var(--yellow); }
.ctx-tf-btn.active {
  background: var(--yellow);
  color: #000;
  border-color: var(--yellow);
  font-weight: 600;
}
.ctx-num {
  width: 80px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
}
.ctx-hint { font-size: 11px; color: var(--text-muted); }
.ctx-preview code {
  background: var(--bg-elevated);
  color: var(--yellow);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-family: 'Consolas', monospace;
}
.ctx-preview code.more { color: var(--text-muted); background: transparent; }
</style>