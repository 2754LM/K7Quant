<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  language: { type: String, default: 'python' },
  height: { type: String, default: '320px' },
})
const emit = defineEmits(['update:modelValue'])

const el = ref(null)
let editor = null
let monacoMod = null

onMounted(async () => {
  // 懒加载 monaco + worker, 避免初始 bundle 拉入 ~4MB
  const [monaco, { default: EditorWorker }] = await Promise.all([
    import('monaco-editor/esm/vs/editor/editor.api'),
    import('monaco-editor/esm/vs/editor/editor.worker?worker'),
  ])
  if (!window.__k7MonacoEnv) {
    self.MonacoEnvironment = { getWorker: () => new EditorWorker() }
    window.__k7MonacoEnv = true
  }
  monacoMod = monaco
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

onBeforeUnmount(() => {
  if (editor) editor.dispose()
  editor = null
  monacoMod = null
})
</script>

<template>
  <div ref="el" class="monaco-host" :style="{ height }">
    <div v-if="!loaded" class="monaco-loading">加载编辑器...</div>
  </div>
</template>

<style scoped>
.monaco-host {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.monaco-loading {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--text-muted); font-size: 12px;
}
</style>
