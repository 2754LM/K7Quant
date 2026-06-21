<script setup>
import { ref, onMounted, computed, nextTick, inject } from 'vue'
import {
  getStrategies, getStrategyTemplates, validateStrategyCode,
  createStrategy, deleteStrategy, updateStrategy, getDslDocs,
} from '../api'

import StrategyPicker from '../components/StrategyPicker.vue'
import StateView from '../components/StateView.vue'

const cfg = inject('cfg')
const reloadCfg = inject('reload')

const strategies = ref([])
const templates = ref({ builtin: [], blank_template: '' })
const selectedId = ref(null)
const editForm = ref({ name: '', description: '', category: 'custom', code: '', params_schema: {} })
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
]
const dslTab = ref('overview')
const funcCatFilter = ref('全部')
const functionCategories = computed(() => {
  const cats = ['全部']
  if (dslDocs.value?.functions) cats.push(...dslDocs.value.functions.map(c => c.cat))
  return cats
})
let validationTimer = null

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
      code: s.code, params_schema: s.params_schema,
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
    code: templates.value.blank_template || 'signal = MA(close, 7) > MA(close, 25)\n止损 = 0.05\n止盈 = 0.10\n仓位 = 1.0',
    params_schema: {},
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
    params_schema: t.params_schema,
  }
  validate()
}

function validate() {
  if (validationTimer) clearTimeout(validationTimer)
  validationTimer = setTimeout(async () => {
    try {
      const res = await validateStrategyCode(editForm.value.code)
      validation.value = res.data
    } catch (e) {
      validation.value = { ok: false, error: e.message }
    }
  }, 500)
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
          :class="['strategy-item', { active: s.id === selectedId, builtin: s.is_builtin }]"
          @click="selectStrategy(s.id)">
          <div class="name">{{ s.name }}
            <span v-if="s.is_builtin" class="badge-sm">预置</span>
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
          <div class="form-group grow">
            <label>策略代码 (DSL)</label>
            <textarea v-model="editForm.code" @input="validate" rows="16"
              class="code-area"></textarea>
            <div class="hint">
              signal = 表达式 (必需) | 止损/止盈/仓位/频率 (可选)
            </div>
          </div>
        </div>
        <div class="validation" v-if="validation">
          <span v-if="validation.ok" class="ok">✓ 语法正确</span>
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
</style>