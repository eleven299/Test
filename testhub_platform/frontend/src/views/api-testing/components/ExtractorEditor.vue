<template>
  <div class="extractor-editor">
    <div class="editor-hint">{{ $t('apiTesting.interface.extractorsHint') }}</div>
    <div class="header-row">
      <el-button size="small" type="primary" :icon="Plus" @click="add">
        {{ $t('apiTesting.interface.addExtractor') }}
      </el-button>
    </div>

    <div v-if="modelValue.length === 0" class="empty">
      <p>{{ $t('apiTesting.interface.extractorNoRecords') }}</p>
      <el-button size="small" type="primary" :icon="Plus" @click="add">
        {{ $t('apiTesting.interface.addFirstExtractor') }}
      </el-button>
    </div>

    <div
      v-for="(item, index) in modelValue"
      :key="index"
      class="extractor-row"
    >
      <el-input
        v-model="item.name"
        :placeholder="$t('apiTesting.interface.extractorName')"
        size="small"
        class="col-name"
      />

      <el-select
        v-model="item.source"
        :placeholder="$t('apiTesting.interface.extractorSource')"
        size="small"
        class="col-source"
        @change="onSourceChange(item)"
      >
        <el-option
          v-for="opt in sourceOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>

      <el-input
        v-if="needsExpression(item.source)"
        v-model="item.expression"
        :placeholder="expressionHint(item.source)"
        size="small"
        class="col-expr"
      />

      <el-input-number
        v-if="item.source === 'regex'"
        v-model="item.group"
        :min="0"
        size="small"
        class="col-group"
        :placeholder="$t('apiTesting.interface.extractorGroup')"
      />

      <el-select
        v-model="item.target_scope"
        :placeholder="$t('apiTesting.interface.extractorScope')"
        size="small"
        class="col-scope"
      >
        <el-option
          v-for="opt in scopeOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>

      <el-input
        v-model="item.default"
        :placeholder="$t('apiTesting.interface.extractorDefault')"
        size="small"
        class="col-default"
      />

      <el-button
        size="small"
        type="danger"
        :icon="Delete"
        circle
        @click="remove(index)"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  }
})
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()

const SOURCES = ['json_body', 'header', 'status_code', 'regex', 'raw_body', 'xml_body']
const SCOPES = ['extracted', 'request', 'global']

const sourceOptions = computed(() =>
  SOURCES.map((s) => ({
    value: s,
    label: t(`apiTesting.interface.extractorSources.${s}`)
  }))
)

const scopeOptions = computed(() =>
  SCOPES.map((s) => ({
    value: s,
    label: t(`apiTesting.interface.extractorScopes.${s}`)
  }))
)

function needsExpression(source) {
  return source !== 'status_code' && source !== 'raw_body'
}

function expressionHint(source) {
  const key = `apiTesting.interface.extractorExpressionHint.${source}`
  const translated = t(key)
  return translated === key ? t('apiTesting.interface.extractorExpression') : translated
}

function onSourceChange(item) {
  if (item.source === 'regex') {
    if (item.group === undefined || item.group === null) {
      item.group = 0
    }
  } else {
    item.group = 0
  }
  if (item.source === 'status_code' || item.source === 'raw_body') {
    item.expression = ''
  }
}

function add() {
  const next = [...props.modelValue]
  next.push({
    name: `var_${next.length + 1}`,
    source: 'json_body',
    expression: '',
    target_scope: 'extracted',
    group: 0,
    default: ''
  })
  emit('update:modelValue', next)
}

function remove(index) {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.extractor-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.editor-hint {
  color: #909399;
  font-size: 12px;
  margin-bottom: 4px;
}

.header-row {
  display: flex;
  justify-content: flex-start;
}

.empty {
  text-align: center;
  padding: 16px;
  background: #fafafa;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
  font-size: 13px;
  color: #909399;
}

.empty p {
  margin: 0 0 8px;
}

.extractor-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1.4fr 100px 1fr 1fr 32px;
  gap: 6px;
  align-items: center;
  padding: 8px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #ffffff;
}

.col-name :deep(.el-input__wrapper),
.col-source :deep(.el-input__wrapper),
.col-expr :deep(.el-input__wrapper),
.col-scope :deep(.el-input__wrapper),
.col-default :deep(.el-input__wrapper) {
  background: transparent;
}
</style>
