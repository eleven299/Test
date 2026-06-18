<template>
  <div class="script-editor">
    <div class="toolbar">
      <el-tag size="small" type="info">Python</el-tag>
      <el-tag v-if="phase === 'post'" size="small" type="success">
        {{ $t('apiTesting.component.scriptEditor.phasePost') }}
      </el-tag>
      <el-tag v-else size="small" type="warning">
        {{ $t('apiTesting.component.scriptEditor.phasePre') }}
      </el-tag>
      <span class="spacer"></span>
      <el-tooltip
        :content="$t('apiTesting.component.scriptEditor.toggleHelp')"
        placement="top"
      >
        <el-button
          size="small"
          :icon="QuestionFilled"
          @click="showHelp = !showHelp"
        />
      </el-tooltip>
    </div>

    <el-collapse-transition>
      <div v-show="showHelp" class="help-panel">
        <div class="help-section">
          <div class="help-title">ctx API</div>
          <ul>
            <li><code>ctx.vars.&lt;name&gt;</code> — {{ $t('apiTesting.component.scriptEditor.helpVars') }}</li>
            <li><code>ctx.request</code> — {{ $t('apiTesting.component.scriptEditor.helpRequest') }}</li>
            <li><code>ctx.response</code> — {{ $t('apiTesting.component.scriptEditor.helpResponse') }}</li>
            <li><code>ctx.log(msg)</code> — {{ $t('apiTesting.component.scriptEditor.helpLog') }}</li>
          </ul>
        </div>
        <div class="help-section">
          <div class="help-title">{{ $t('apiTesting.component.scriptEditor.helpInjectedTitle') }}</div>
          <p class="help-inline"><code>json</code> · <code>re</code> · <code>time</code> · <code>datetime</code> · <code>hashlib</code> · <code>base64</code> · <code>math</code> · <code>random</code></p>
        </div>
        <div class="help-section">
          <div class="help-title">{{ $t('apiTesting.component.scriptEditor.helpExampleTitle') }}</div>
          <pre class="help-example">{{ exampleCode }}</pre>
        </div>
      </div>
    </el-collapse-transition>

    <div
      ref="containerRef"
      class="monaco-container"
      :style="{ height: height + 'px' }"
    ></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import * as monaco from 'monaco-editor'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  phase: {
    type: String,
    default: 'pre',
    validator: (v) => ['pre', 'post'].includes(v)
  },
  height: {
    type: Number,
    default: 320
  },
  readOnly: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()

const containerRef = ref(null)
const showHelp = ref(false)
let editor = null
let suppressChange = false

const exampleCode = computedExample()

function computedExample() {
  if (props.phase === 'post') {
    return [
      '# 从响应提取 token,并算签名',
      "data = ctx.response.json()",
      "ctx.vars.token = data['data']['access_token']",
      "ts = str(int(time.time()))",
      "ctx.vars.sign = hashlib.md5(f\"{ctx.vars.token}{ts}\".encode()).hexdigest()",
      "ctx.vars.timestamp = ts"
    ].join('\n')
  }
  return [
    '# 前置:为当前请求预计算变量',
    "ts = str(int(time.time()))",
    "ctx.vars.timestamp = ts",
    "ctx.vars.nonce = hashlib.md5(ts.encode()).hexdigest()"
  ].join('\n')
}

function initEditor() {
  if (!containerRef.value) return
  editor = monaco.editor.create(containerRef.value, {
    value: props.modelValue || '',
    language: 'python',
    theme: 'vs',
    automaticLayout: true,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    fontSize: 13,
    lineHeight: 20,
    tabSize: 4,
    insertSpaces: true,
    wordWrap: 'on',
    lineNumbers: 'on',
    renderLineHighlight: 'line',
    smoothCursorAnimation: 'off',
    cursorBlinking: 'smooth',
    readOnly: props.readOnly,
    scrollbar: {
      verticalScrollbarSize: 10,
      horizontalScrollbarSize: 10
    }
  })

  editor.onDidChangeModelContent(() => {
    if (suppressChange) return
    emit('update:modelValue', editor.getValue())
  })
}

watch(
  () => props.modelValue,
  (newVal) => {
    if (!editor) return
    const current = editor.getValue()
    if (newVal !== current) {
      suppressChange = true
      editor.setValue(newVal || '')
      suppressChange = false
    }
  }
)

watch(
  () => props.readOnly,
  (newVal) => {
    if (editor) editor.updateOptions({ readOnly: newVal })
  }
)

onMounted(async () => {
  await nextTick()
  initEditor()
})

onBeforeUnmount(() => {
  if (editor) {
    editor.dispose()
    editor = null
  }
})

defineExpose({
  focus: () => editor?.focus(),
  getValue: () => editor?.getValue() || ''
})
</script>

<style scoped>
.script-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar .spacer {
  flex: 1;
}

.help-panel {
  background: #f6f8fa;
  border: 1px solid #d0d7de;
  border-radius: 4px;
  padding: 12px 16px;
  font-size: 12px;
  color: #57606a;
}

.help-section {
  margin-bottom: 10px;
}

.help-section:last-child {
  margin-bottom: 0;
}

.help-title {
  font-weight: 600;
  color: #24292f;
  margin-bottom: 4px;
}

.help-section ul {
  margin: 0;
  padding-left: 18px;
}

.help-section li {
  line-height: 1.8;
}

.help-inline {
  margin: 0;
  line-height: 1.8;
}

.help-example {
  background: #ffffff;
  border: 1px solid #d0d7de;
  border-radius: 3px;
  padding: 8px 10px;
  margin: 4px 0 0;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  white-space: pre;
  overflow-x: auto;
  color: #1f2328;
}

.help-panel code {
  background: #ffffff;
  border: 1px solid #d0d7de;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  color: #1f2328;
}

.monaco-container {
  width: 100%;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}
</style>
