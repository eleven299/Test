<template>
  <div class="assertion-editor">
    <div class="header-row">
      <el-button size="small" type="primary" :icon="Plus" @click="add">
        {{ $t('apiTesting.component.assertionEditor.add') }}
      </el-button>
    </div>

    <div v-if="modelValue.length === 0" class="empty">
      {{ $t('apiTesting.component.assertionEditor.noData') }}
    </div>

    <div
      v-for="(item, index) in modelValue"
      :key="index"
      class="assertion-row"
      :class="{ legacy: !!item._legacy }"
    >
      <el-checkbox v-model="item.enabled" />

      <el-input
        v-model="item.name"
        :placeholder="$t('apiTesting.component.assertionEditor.columnName')"
        size="small"
        class="col-name"
      />

      <el-select
        v-model="item.source"
        size="small"
        class="col-source"
        :placeholder="$t('apiTesting.component.assertionEditor.columnSource')"
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

      <el-select
        v-model="item.operator"
        size="small"
        class="col-op"
        :placeholder="$t('apiTesting.component.assertionEditor.columnOperator')"
        @change="onOperatorChange(item)"
      >
        <el-option
          v-for="opt in availableOperators(item.source)"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>

      <div class="col-expected-wrap">
        <el-input
          v-if="needsExpected(item.operator)"
          v-model="item.expected"
          :placeholder="expectedHint(item.operator)"
          size="small"
        />
        <slot
          name="expected-extras"
          :item="item"
          :index="index"
          :needs-expected="needsExpected(item.operator)"
        />
      </div>

      <el-input
        v-model="item.message"
        :placeholder="$t('apiTesting.component.assertionEditor.columnMessage')"
        size="small"
        class="col-message"
      />

      <el-button
        size="small"
        type="danger"
        :icon="Delete"
        circle
        @click="remove(index)"
      />
    </div>

    <div v-if="hasLegacy" class="legacy-hint">
      <el-icon><InfoFilled /></el-icon>
      {{ $t('apiTesting.component.assertionEditor.legacyHint') }}
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import { Plus, Delete, InfoFilled } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  }
})
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()

const SOURCES = [
  'status_code',
  'response_time',
  'json_body',
  'header',
  'raw_body'
]

const OPERATORS_BY_SOURCE = {
  status_code: ['equals', 'not_equals', 'in_array', 'not_in_array'],
  response_time: ['less_equal', 'less_than', 'greater_than', 'greater_equal', 'equals'],
  json_body: [
    'equals', 'not_equals', 'contains', 'not_contains',
    'greater_than', 'less_than', 'greater_equal', 'less_equal',
    'in_array', 'not_in_array', 'regex', 'length_eq',
    'exists', 'not_exists', 'type_is'
  ],
  header: ['equals', 'not_equals', 'contains', 'not_contains', 'regex', 'exists', 'not_exists'],
  raw_body: ['equals', 'not_equals', 'contains', 'not_contains', 'regex', 'length_eq', 'exists', 'not_exists']
}

const LEGACY_MAP = {
  status_code:   { source: 'status_code',   operator: 'equals',     expectedKey: 'expected' },
  response_time: { source: 'response_time', operator: 'less_equal', expectedKey: 'expected' },
  contains:      { source: 'raw_body',      operator: 'contains',   expectedKey: 'expected' },
  json_path:     { source: 'json_body',     operator: 'equals',     expectedKey: 'expected', expressionKey: 'json_path' },
  header:        { source: 'header',        operator: 'equals',     expectedKey: 'expected_value', expressionKey: 'header_name' },
  equals:        { source: 'raw_body',      operator: 'equals',     expectedKey: 'expected' }
}

function normalizeLegacy(item) {
  if (!item || typeof item !== 'object') return null
  if (item.source && item.operator) return item
  const legacyType = item.type
  if (!legacyType || !LEGACY_MAP[legacyType]) {
    return {
      enabled: item.enabled !== false,
      name: item.name || 'unnamed',
      source: 'raw_body',
      expression: '',
      operator: 'equals',
      expected: item.expected ?? '',
      message: item.message || '',
      _legacy: true
    }
  }
  const m = LEGACY_MAP[legacyType]
  const expected = item[m.expectedKey] ?? item.expected ?? ''
  const expression = m.expressionKey ? (item[m.expressionKey] || '') : ''
  return {
    enabled: item.enabled !== false,
    name: item.name || 'unnamed',
    source: m.source,
    expression,
    operator: m.operator,
    expected,
    message: item.message || '',
    _legacy: true
  }
}

function maybeNormalizeAll() {
  if (!Array.isArray(props.modelValue)) return
  let changed = false
  const next = props.modelValue.map((item) => {
    if (!item || item.type || (!item.source && !item.operator)) {
      changed = true
      return normalizeLegacy(item)
    }
    return item
  })
  if (changed) {
    emit('update:modelValue', next.filter(Boolean))
  }
}

onMounted(maybeNormalizeAll)
watch(() => props.modelValue, maybeNormalizeAll, { deep: false })

const sourceOptions = computed(() =>
  SOURCES.map((s) => ({
    value: s,
    label: t(`apiTesting.component.assertionEditor.source${camelize(s)}`)
  }))
)

function camelize(s) {
  return s.replace(/_([a-z])/g, (_, c) => c.toUpperCase())
}

function opLabel(op) {
  const key = `apiTesting.component.assertionEditor.op${camelize(op)}`
  const translated = t(key)
  return translated === key ? op : translated
}

function availableOperators(source) {
  const list = OPERATORS_BY_SOURCE[source] || ['equals']
  return list.map((op) => ({ value: op, label: opLabel(op) }))
}

function needsExpression(source) {
  return source !== 'status_code' && source !== 'response_time'
}

function needsExpected(operator) {
  return !['exists', 'not_exists'].includes(operator)
}

function expressionHint(source) {
  if (source === 'json_body') return '$.data.id'
  if (source === 'header') return 'X-User-Id'
  if (source === 'raw_body') return ''
  return ''
}

function expectedHint(operator) {
  if (['in_array', 'not_in_array'].includes(operator)) return 'v1,v2,v3'
  if (operator === 'type_is') return 'int | str | list | dict | bool'
  if (operator === 'length_eq') return '5'
  if (operator === 'regex') return '\\d{4}'
  return ''
}

function defaultOperatorFor(source) {
  if (source === 'response_time') return 'less_equal'
  return 'equals'
}

function defaultExpectedFor(source) {
  if (source === 'status_code') return 200
  if (source === 'response_time') return 1000
  return ''
}

function onSourceChange(item) {
  const allowed = OPERATORS_BY_SOURCE[item.source] || ['equals']
  if (!allowed.includes(item.operator)) {
    item.operator = defaultOperatorFor(item.source)
  }
  if (!needsExpression(item.source)) {
    item.expression = ''
  }
  if (item.source === 'status_code' || item.source === 'response_time') {
    item.expected = defaultExpectedFor(item.source)
  }
}

function onOperatorChange(item) {
  if (!needsExpected(item.operator)) {
    item.expected = ''
  }
}

function add() {
  const next = [...props.modelValue]
  next.push({
    enabled: true,
    name: `assertion_${next.length + 1}`,
    source: 'status_code',
    expression: '',
    operator: 'equals',
    expected: 200,
    message: ''
  })
  emit('update:modelValue', next)
}

function remove(index) {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emit('update:modelValue', next)
}

const hasLegacy = computed(() =>
  props.modelValue.some((item) => !!item._legacy)
)

defineExpose({
  normalizeAll() {
    return props.modelValue.map((item) => {
      const { _legacy, ...rest } = item
      return rest
    })
  }
})
</script>

<style scoped>
.assertion-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.header-row {
  display: flex;
  justify-content: flex-start;
}

.empty {
  color: #909399;
  text-align: center;
  padding: 16px;
  background: #fafafa;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
  font-size: 13px;
}

.assertion-row {
  display: grid;
  grid-template-columns: 32px 1.2fr 1fr 1.4fr 1fr 1.6fr 1.4fr 32px;
  gap: 6px;
  align-items: center;
  padding: 8px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #ffffff;
}

.assertion-row.legacy {
  background: #fdf6ec;
  border-color: #f5dab1;
}

.col-name :deep(.el-input__wrapper),
.col-source :deep(.el-input__wrapper),
.col-expr :deep(.el-input__wrapper),
.col-op :deep(.el-input__wrapper),
.col-message :deep(.el-input__wrapper) {
  background: transparent;
}

.col-expected-wrap {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.col-expected-wrap :deep(.el-input) {
  flex: 1;
  min-width: 0;
}

.legacy-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #e6a23c;
  font-size: 12px;
  margin-top: 4px;
}
</style>
