<script setup>
import { ref, computed, watch } from 'vue'

// 规则: { field: 'rsi', op: '<', value: 30 }
// 字段: rsi / macd_hist / close / volume / ...
// 算子: > < >= <= == !=
// 数值: 数字

const props = defineProps({
  modelValue: { type: Array, default: () => [] },   // [{field, op, value}]
  fields: { type: Array, default: () => [] },         // 可用字段 [{id, name_zh, type: 'number'|'pct'}]
  defaultField: { type: String, default: '' },
  maxRules: { type: Number, default: 5 },
})
const emit = defineEmits(['update:modelValue', 'change'])

const OPS = [
  { id: '<', label: '<' },
  { id: '<=', label: '≤' },
  { id: '==', label: '=' },
  { id: '!=', label: '≠' },
  { id: '>=', label: '≥' },
  { id: '>', label: '>' },
]

// 内部维护
const rules = ref([...props.modelValue])

watch(() => props.modelValue, (v) => {
  if (JSON.stringify(v) !== JSON.stringify(rules.value)) {
    rules.value = [...v]
  }
})

function add() {
  if (rules.value.length >= props.maxRules) return
  rules.value.push({ field: props.defaultField || props.fields[0]?.id || '', op: '<', value: 0 })
  emitChange()
}
function del(i) {
  rules.value.splice(i, 1)
  emitChange()
}
function emitChange() {
  emit('update:modelValue', [...rules.value])
  emit('change', [...rules.value])
}
function getField(id) {
  return props.fields.find(f => f.id === id)
}
</script>

<template>
  <div class="rule-builder">
    <div v-for="(r, i) in rules" :key="i" class="rule">
      <select v-model="r.field" @change="emitChange">
        <option v-for="f in fields" :key="f.id" :value="f.id">{{ f.name_zh || f.id }}</option>
      </select>
      <select v-model="r.op" @change="emitChange">
        <option v-for="o in OPS" :key="o.id" :value="o.id">{{ o.label }}</option>
      </select>
      <input type="number" v-model.number="r.value" step="any" @change="emitChange" />
      <button class="del" @click="del(i)">×</button>
    </div>
    <button class="add" @click="add" :disabled="rules.length >= maxRules">+ 添加条件</button>
  </div>
</template>

<style scoped>
.rule-builder { display: flex; flex-direction: column; gap: 6px; }
.rule {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px;
}
.rule select, .rule input {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
}
.rule input { width: 90px; }
.rule input:focus, .rule select:focus { border-color: var(--yellow); outline: none; }
.rule .del {
  background: transparent;
  color: var(--text-muted);
  padding: 0 6px;
  font-size: 16px;
  line-height: 1;
}
.rule .del:hover { color: var(--red); }
.add {
  background: transparent;
  color: var(--yellow);
  border: 1px dashed var(--border);
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  align-self: flex-start;
}
.add:hover { border-color: var(--yellow); }
.add:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
