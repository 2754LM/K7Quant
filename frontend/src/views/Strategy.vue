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
const dslDocs = ref({ syntax: '', examples: [] })
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

      <div class="card">
        <h3>DSL 语法速查</h3>
        <pre class="docs">{{ dslDocs.syntax }}</pre>
        <h4>示例</h4>
        <div v-for="ex in dslDocs.examples" :key="ex.name" class="example">
          <div class="ex-name">{{ ex.name }}</div>
          <pre class="ex-code">{{ ex.code }}</pre>
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
.example { margin-bottom: 12px; }
.ex-name { font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
.ex-code {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--yellow);
  font-family: 'Consolas', monospace;
}
</style>