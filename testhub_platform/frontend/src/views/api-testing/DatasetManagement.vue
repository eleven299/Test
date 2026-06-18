<template>
  <div class="dataset-management">
    <div class="page-header">
      <h3>{{ $t('apiTesting.dataset.title') }}</h3>
      <div class="actions">
        <el-select
          v-model="filters.project"
          :placeholder="$t('apiTesting.common.selectProject')"
          clearable
          style="width: 220px;"
          @change="loadList"
        >
          <el-option
            v-for="p in projects"
            :key="p.id"
            :label="p.name"
            :value="p.id"
          />
        </el-select>
        <el-input
          v-model="filters.search"
          :placeholder="$t('apiTesting.dataset.searchPlaceholder')"
          clearable
          style="width: 220px;"
          @clear="loadList"
          @keyup.enter="loadList"
        >
          <template #append>
            <el-button :icon="Search" @click="loadList" />
          </template>
        </el-input>
        <el-button type="primary" :icon="Plus" @click="onCreate">
          {{ $t('apiTesting.dataset.create') }}
        </el-button>
      </div>
    </div>

    <el-table
      v-loading="loading"
      :data="list"
      stripe
      border
      style="width: 100%"
    >
      <el-table-column prop="name" :label="$t('apiTesting.dataset.columnName')" min-width="160" />
      <el-table-column prop="project_name" :label="$t('apiTesting.dataset.columnProject')" width="160" />
      <el-table-column prop="format_display" :label="$t('apiTesting.dataset.columnFormat')" width="100" />
      <el-table-column prop="row_count" :label="$t('apiTesting.dataset.columnRowCount')" width="90" align="center" />
      <el-table-column prop="description" :label="$t('apiTesting.dataset.columnDescription')" min-width="200" show-overflow-tooltip />
      <el-table-column :label="$t('apiTesting.dataset.columnUpdatedAt')" width="170">
        <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column :label="$t('apiTesting.common.actions')" width="280" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="onEditData(row)">{{ $t('apiTesting.dataset.btnEditData') }}</el-button>
          <el-button size="small" type="primary" @click="onEdit(row)">{{ $t('apiTesting.dataset.btnEdit') }}</el-button>
          <el-button size="small" type="info" @click="onImportCsv(row)">{{ $t('apiTesting.dataset.btnImportCsv') }}</el-button>
          <el-button size="small" type="danger" @click="onDelete(row)">{{ $t('apiTesting.common.delete') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-row">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadList"
        @size-change="loadList"
      />
    </div>

    <el-dialog
      v-model="metaDialogVisible"
      :title="form.id ? $t('apiTesting.dataset.editTitle') : $t('apiTesting.dataset.createTitle')"
      width="640px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item :label="$t('apiTesting.dataset.columnProject')" prop="project">
          <el-select v-model="form.project" :placeholder="$t('apiTesting.common.selectProject')" style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.dataset.columnName')" prop="name">
          <el-input v-model="form.name" :placeholder="$t('apiTesting.dataset.namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.dataset.columnFormat')" prop="format">
          <el-radio-group v-model="form.format">
            <el-radio value="inline">{{ $t('apiTesting.dataset.formatInline') }}</el-radio>
            <el-radio value="csv">{{ $t('apiTesting.dataset.formatCsv') }}</el-radio>
            <el-radio value="json">{{ $t('apiTesting.dataset.formatJson') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.dataset.columnDescription')" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="metaDialogVisible = false">{{ $t('apiTesting.common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmitMeta">{{ $t('apiTesting.common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="dataDialogVisible"
      :title="$t('apiTesting.dataset.dataEditorTitle') + ' - ' + (currentDataset?.name || '')"
      width="900px"
      :close-on-click-modal="false"
    >
      <div class="data-editor-toolbar">
        <el-button :icon="Plus" size="small" @click="addRow">{{ $t('apiTesting.dataset.addRow') }}</el-button>
        <el-text size="small" type="info" style="margin-left: 12px;">
          {{ $t('apiTesting.dataset.dataHint') }}
        </el-text>
      </div>
      <el-table :data="dataRows" border size="small" max-height="500" style="width: 100%">
        <el-table-column type="index" :label="$t('apiTesting.dataset.columnRowIndex')" width="60" fixed />
        <el-table-column
          v-for="col in columns"
          :key="col"
          :prop="col"
          :label="col"
          min-width="160"
        >
          <template #default="{ row, $index }">
            <el-input v-model="row[col]" size="small" @keyup.delete.stop="onDeleteKey($event, $index, col)" />
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.common.actions')" width="120" fixed="right">
          <template #default="{ $index }">
            <el-button size="small" type="danger" :icon="Delete" circle @click="removeRow($index)" />
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-hint">{{ $t('apiTesting.dataset.emptyHint') }}</div>
        </template>
      </el-table>
      <div class="add-column-row">
        <el-input
          v-model="newColumnName"
          size="small"
          style="width: 200px;"
          :placeholder="$t('apiTesting.dataset.newColumnName')"
          @keyup.enter="addColumn"
        />
        <el-button size="small" @click="addColumn">{{ $t('apiTesting.dataset.addColumn') }}</el-button>
      </div>
      <template #footer>
        <el-button @click="dataDialogVisible = false">{{ $t('apiTesting.common.close') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmitData">{{ $t('apiTesting.common.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="csvDialogVisible"
      :title="$t('apiTesting.dataset.csvImportTitle') + ' - ' + (currentDataset?.name || '')"
      width="540px"
    >
      <el-form label-width="120px">
        <el-form-item :label="$t('apiTesting.dataset.csvFile')">
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="onCsvPicked"
            :on-exceed="onCsvExceed"
            accept=".csv,text/csv"
          >
            <el-button :icon="UploadFilled">{{ $t('apiTesting.dataset.pickCsv') }}</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.dataset.csvHasHeader')">
          <el-switch v-model="csvHasHeader" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.dataset.csvEncoding')">
          <el-select v-model="csvEncoding" style="width: 200px">
            <el-option label="UTF-8" value="utf-8" />
            <el-option label="GBK" value="gbk" />
            <el-option label="Big5" value="big5" />
          </el-select>
        </el-form-item>
      </el-form>
      <div v-if="csvPreview" class="csv-preview">
        <el-text size="small" type="success">
          {{ $t('apiTesting.dataset.previewReady', { rows: csvPreview.row_count, cols: csvPreview.columns.length }) }}
        </el-text>
      </div>
      <template #footer>
        <el-button @click="csvDialogVisible = false">{{ $t('apiTesting.common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" :disabled="!csvFile" @click="onSubmitCsv">
          {{ $t('apiTesting.dataset.confirmImport') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Search, UploadFilled } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import {
  getDatasets, createDataset, updateDataset, deleteDataset,
  importDatasetCsv, getApiProjects
} from '@/api/api-testing'

const { t } = useI18n()

const projects = ref([])
const list = ref([])
const loading = ref(false)
const submitting = ref(false)

const filters = reactive({
  project: null,
  search: ''
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const formRef = ref(null)
const metaDialogVisible = ref(false)
const form = reactive({
  id: null,
  project: null,
  name: '',
  format: 'inline',
  description: ''
})
const rules = {
  project: [{ required: true, message: t('apiTesting.common.selectProject'), trigger: 'change' }],
  name: [{ required: true, message: t('apiTesting.dataset.nameRequired'), trigger: 'blur' }]
}

const dataDialogVisible = ref(false)
const currentDataset = ref(null)
const dataRows = ref([])
const columns = ref([])
const newColumnName = ref('')

const csvDialogVisible = ref(false)
const csvFile = ref(null)
const csvHasHeader = ref(true)
const csvEncoding = ref('utf-8')
const csvPreview = ref(null)

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

async function loadProjects() {
  try {
    const res = await getApiProjects({ page_size: 200 })
    projects.value = res.data?.results || res.data || []
  } catch (e) {
    ElMessage.error(t('apiTesting.dataset.loadProjectsFailed'))
  }
}

async function loadList() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize
    }
    if (filters.project) params.project = filters.project
    if (filters.search) params.search = filters.search
    const res = await getDatasets(params)
    list.value = res.data?.results || []
    pagination.total = res.data?.count || list.value.length
  } catch (e) {
    ElMessage.error(t('apiTesting.dataset.loadFailed'))
  } finally {
    loading.value = false
  }
}

function onCreate() {
  Object.assign(form, { id: null, project: null, name: '', format: 'inline', description: '' })
  metaDialogVisible.value = true
}

function onEdit(row) {
  Object.assign(form, {
    id: row.id,
    project: row.project,
    name: row.name,
    format: row.format,
    description: row.description || ''
  })
  metaDialogVisible.value = true
}

async function onSubmitMeta() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = {
        project: form.project,
        name: form.name,
        format: form.format,
        description: form.description
      }
      if (form.id) {
        await updateDataset(form.id, payload)
        ElMessage.success(t('apiTesting.dataset.updateSuccess'))
      } else {
        const res = await createDataset(payload)
        ElMessage.success(t('apiTesting.dataset.createSuccess'))
        metaDialogVisible.value = false
        onEditData(res.data)
        return
      }
      metaDialogVisible.value = false
      loadList()
    } catch (e) {
      ElMessage.error(e?.response?.data?.detail || t('apiTesting.dataset.submitFailed'))
    } finally {
      submitting.value = false
    }
  })
}

function onEditData(row) {
  currentDataset.value = row
  dataRows.value = Array.isArray(row.data) ? row.data.map((r) => ({ ...r })) : []
  const colSet = new Set(row.columns || [])
  dataRows.value.forEach((r) => Object.keys(r).forEach((k) => colSet.add(k)))
  columns.value = Array.from(colSet)
  dataDialogVisible.value = true
}

function addRow() {
  const row = {}
  columns.value.forEach((c) => (row[c] = ''))
  dataRows.value.push(row)
}

function removeRow(idx) {
  dataRows.value.splice(idx, 1)
}

function addColumn() {
  const name = (newColumnName.value || '').trim()
  if (!name) {
    ElMessage.warning(t('apiTesting.dataset.columnNameEmpty'))
    return
  }
  if (columns.value.includes(name)) {
    ElMessage.warning(t('apiTesting.dataset.columnNameDuplicate'))
    return
  }
  columns.value.push(name)
  dataRows.value.forEach((r) => (r[name] = ''))
  newColumnName.value = ''
}

function onDeleteKey(_event, _idx, _col) {
  // 占位:预留删除列的快捷键入口
}

async function onSubmitData() {
  submitting.value = true
  try {
    await updateDataset(currentDataset.value.id, {
      data: dataRows.value,
      columns: columns.value
    })
    ElMessage.success(t('apiTesting.dataset.saveSuccess'))
    dataDialogVisible.value = false
    loadList()
  } catch (e) {
    ElMessage.error(t('apiTesting.dataset.saveFailed'))
  } finally {
    submitting.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      t('apiTesting.dataset.deleteConfirm', { name: row.name }),
      t('apiTesting.common.confirm'),
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await deleteDataset(row.id)
    ElMessage.success(t('apiTesting.dataset.deleteSuccess'))
    loadList()
  } catch (e) {
    ElMessage.error(t('apiTesting.dataset.deleteFailed'))
  }
}

function onImportCsv(row) {
  currentDataset.value = row
  csvFile.value = null
  csvPreview.value = null
  csvHasHeader.value = true
  csvEncoding.value = 'utf-8'
  csvDialogVisible.value = true
}

function onCsvPicked(file) {
  csvFile.value = file.raw
  csvPreview.value = null
}

function onCsvExceed() {
  ElMessage.warning(t('apiTesting.dataset.csvExceedHint'))
}

async function onSubmitCsv() {
  if (!csvFile.value) return
  submitting.value = true
  try {
    const res = await importDatasetCsv(
      currentDataset.value.id,
      csvFile.value,
      csvHasHeader.value,
      csvEncoding.value
    )
    csvPreview.value = res.data
    ElMessage.success(
      t('apiTesting.dataset.importSuccess', { rows: res.data.row_count })
    )
    csvDialogVisible.value = false
    loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || t('apiTesting.dataset.importFailed'))
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await loadProjects()
  await loadList()
})
</script>

<style scoped>
.dataset-management {
  padding: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}

.page-header h3 {
  margin: 0;
}

.page-header .actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pagination-row {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.data-editor-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.add-column-row {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}

.empty-hint {
  padding: 20px;
  color: #909399;
  font-size: 13px;
  text-align: center;
}

.csv-preview {
  margin-top: 12px;
}
</style>
