<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'

// Vite 下为 monaco 提供基础 worker (语法高亮走主线程 Monarch, 无需语言服务 worker)
if (!window.__k7MonacoEnv) {
  self.MonacoEnvironment = { getWorker: () => new EditorWorker() }
  window.__k7MonacoEnv = true
}

const props = defineProps({
  modelValue: { type: String, default: '' },
  language: { type: String, default: 'python' },
  height: { type: String, default: '320px' },
})
const emit = defineEmits(['update:modelValue'])

const el = ref(null)
let editor = null

onMounted(() => {
  editor = monaco.editor.create(el.value, {
    value: props.modelValue,
    language: props.language,
    theme: 'vs-dark',
    minimap: { enabled: false },
    fontSize: 13,
    lineNumbers: 'on',
    tabSize: 2,
    scrollBeyondLastLine: false,
    automaticLayout: true,
    renderLineHighlight: 'none',
  })
  editor.onDidChangeModelContent(() => {
    const v = editor.getValue()
    if (v !== props.modelValue) emit('update:modelValue', v)
  })
})

watch(() => props.modelValue, (v) => {
  if (editor && v !== editor.getValue()) editor.setValue(v ?? '')
})

onBeforeUnmount(() => { if (editor) editor.dispose() })
</script>

<template>
  <div ref="el" class="monaco-host" :style="{ height }"></div>
</template>

<style scoped>
.monaco-host {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
</style>
