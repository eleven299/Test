<template>
  <div class="report-view">
    <div class="header">
      <h3>{{ $t('apiTesting.report.title') }}</h3>
      <div class="actions">
        <el-button type="primary" @click="refreshReports">{{ $t('apiTesting.report.refreshReport') }}</el-button>
        <el-button @click="openAllureReport">{{ $t('apiTesting.report.viewAllureReport') }}</el-button>
      </div>
    </div>

    <div class="content">
      <el-table :data="reports" v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="test_suite_name" :label="$t('apiTesting.report.testSuite')" min-width="200" />
        <el-table-column prop="status" :label="$t('apiTesting.common.status')" width="120">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_requests" :label="$t('apiTesting.report.totalRequests')" width="100" />
        <el-table-column prop="passed_requests" :label="$t('apiTesting.report.passedCount')" width="100">
          <template #default="scope">
            <span style="color: #67c23a">{{ scope.row.passed_requests }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="failed_requests" :label="$t('apiTesting.report.failedCount')" width="100">
          <template #default="scope">
            <span style="color: #f56c6c">{{ scope.row.failed_requests }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="executed_by.username" :label="$t('apiTesting.report.executor')" width="120" />
        <el-table-column prop="created_at" :label="$t('apiTesting.report.executionTime')" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.common.operation')" width="220" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="viewReportDetail(scope.row)">
              {{ $t('apiTesting.report.generateAndViewReport') }}
            </el-button>
            <el-button link type="primary" @click="openStepDrawer(scope.row)">
              {{ $t('apiTesting.report.viewStepDetail') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-drawer
      v-model="stepDrawerVisible"
      :title="`${$t('apiTesting.report.stepDetail')} #${currentExecutionId}`"
      direction="rtl"
      size="70%"
    >
      <div v-loading="stepsLoading">
        <el-empty v-if="!stepsLoading && steps.length === 0" :description="$t('apiTesting.report.noSteps')" />

        <el-collapse v-else v-model="activeStepNames">
          <el-collapse-item
            v-for="step in steps"
            :key="step.id"
            :name="step.id"
          >
            <template #title>
              <div class="step-collapse-title">
                <el-tag :type="getStepStatusType(step.status)" size="small">
                  {{ getStepStatusText(step.status) }}
                </el-tag>
                <span class="step-title-text">
                  {{ step.request_name || step.url }}
                  <span v-if="step.method" class="step-method-tag">{{ step.method }}</span>
                </span>
                <span v-if="step.attempt && step.attempt > 1" class="step-attempt">
                  {{ $t('apiTesting.report.attempt') }}: {{ step.attempt }}
                </span>
              </div>
            </template>

            <div class="step-detail-body">
              <div class="step-summary-row">
                <span v-if="step.status_code" class="step-summary-item">
                  <strong>{{ $t('apiTesting.report.statusCode') }}:</strong>
                  <el-tag size="small" :type="step.status_code >= 200 && step.status_code < 300 ? 'success' : 'danger'">
                    {{ step.status_code }}
                  </el-tag>
                </span>
                <span v-if="step.response_time != null" class="step-summary-item">
                  <strong>{{ $t('apiTesting.report.responseTime') }}:</strong>
                  {{ step.response_time.toFixed(0) }}ms
                </span>
                <span v-if="step.iteration != null && step.iteration > 0" class="step-summary-item">
                  <strong>{{ $t('apiTesting.report.iteration') }}:</strong>
                  {{ step.iteration }}
                </span>
              </div>

              <el-tabs class="step-tabs">
                <el-tab-pane :label="$t('apiTesting.report.assertionsResults')" name="assertions">
                  <div v-if="step.assertions_results && step.assertions_results.length">
                    <div
                      v-for="(a, idx) in step.assertions_results"
                      :key="idx"
                      class="assertion-line"
                      :class="{ 'is-passed': a.passed, 'is-failed': !a.passed }"
                    >
                      <span class="assertion-status">{{ a.passed ? '✓' : '✗' }}</span>
                      <span class="assertion-name">{{ a.name || a.assertion || `#${idx + 1}` }}</span>
                      <span v-if="a.error_message || a.error" class="assertion-error">
                        {{ a.error_message || a.error }}
                      </span>
                    </div>
                  </div>
                  <el-empty v-else :description="$t('apiTesting.report.noAssertionsResults')" :image-size="60" />
                </el-tab-pane>

                <el-tab-pane :label="$t('apiTesting.report.extractedVars')" name="extracted">
                  <div v-if="step.extracted_vars && Object.keys(step.extracted_vars).length">
                    <div
                      v-for="(value, key) in step.extracted_vars"
                      :key="key"
                      class="extracted-var-line"
                    >
                      <span class="var-key">{{ key }}:</span>
                      <code class="var-value">{{ formatVarValue(value) }}</code>
                    </div>
                  </div>
                  <el-empty v-else :description="$t('apiTesting.report.noExtractedVars')" :image-size="60" />
                </el-tab-pane>

                <el-tab-pane :label="$t('apiTesting.report.scriptLogs')" name="logs">
                  <pre v-if="step.script_logs && step.script_logs.length" class="script-log-pre">{{ step.script_logs.join('\n') }}</pre>
                  <el-empty v-else :description="$t('apiTesting.report.noScriptLogs')" :image-size="60" />
                </el-tab-pane>

                <el-tab-pane v-if="step.error_message" :label="$t('apiTesting.report.errorMessage')" name="error">
                  <pre class="script-log-pre error-pre">{{ step.error_message }}</pre>
                </el-tab-pane>
              </el-tabs>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import api from '@/utils/api'
import dayjs from 'dayjs'

const { t } = useI18n()
const reports = ref([])
const loading = ref(false)

const stepDrawerVisible = ref(false)
const stepsLoading = ref(false)
const steps = ref([])
const currentExecutionId = ref(null)
const activeStepNames = ref([])

const loadReports = async () => {
  loading.value = true
  try {
    const response = await api.get('/api-testing/test-executions/')
    reports.value = response.data.results || response.data
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.loadReports'))
  } finally {
    loading.value = false
  }
}

const refreshReports = async () => {
  await loadReports()
}

const generateAndOpenAllureReport = async (executionId) => {
  try {
    const response = await api.post(`/api-testing/test-executions/${executionId}/generate-allure-report/`)
    ElMessage.success(t('apiTesting.messages.success.reportGenerated'))
    const fullUrl = `${window.location.origin}${response.data.report_url}`
    window.open(fullUrl, '_blank')
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.reportGenerateFailed'))
  }
}

const openAllureReport = () => {
  ElMessage.info(t('apiTesting.report.selectExecutionTip'))
}

const viewReportDetail = (report) => {
  generateAndOpenAllureReport(report.id)
}

const openStepDrawer = async (report) => {
  currentExecutionId.value = report.id
  stepDrawerVisible.value = true
  steps.value = []
  activeStepNames.value = []
  stepsLoading.value = true
  try {
    const response = await api.get(`/api-testing/test-executions/${report.id}/step-results/`)
    steps.value = response.data.results || []
    if (steps.value.length > 0) {
      activeStepNames.value = [steps.value[0].id]
    }
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.loadReports'))
  } finally {
    stepsLoading.value = false
  }
}

const formatVarValue = (value) => {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch (e) {
    return String(value)
  }
}

const getStatusType = (status) => {
  const typeMap = {
    'PENDING': 'info',
    'RUNNING': 'warning',
    'COMPLETED': 'success',
    'FAILED': 'danger',
    'CANCELLED': 'info'
  }
  return typeMap[status] || 'info'
}

const getStatusText = (status) => {
  const statusKey = {
    'PENDING': 'pending',
    'RUNNING': 'running',
    'COMPLETED': 'completed',
    'FAILED': 'failed',
    'CANCELLED': 'cancelled'
  }[status]
  return statusKey ? t(`apiTesting.report.status.${statusKey}`) : status
}

const getStepStatusType = (status) => {
  const map = {
    'PASSED': 'success',
    'FAILED': 'danger',
    'ERROR': 'danger',
    'SKIPPED': 'info',
    'PENDING': 'info'
  }
  return map[status] || 'info'
}

const getStepStatusText = (status) => {
  const key = (status || '').toLowerCase()
  if (key === 'passed') return t('apiTesting.report.passed')
  if (key === 'failed') return t('apiTesting.report.failed')
  if (key === 'error') return t('apiTesting.report.errored')
  if (key === 'skipped') return t('apiTesting.report.skipped')
  return status || '—'
}

const formatDate = (dateString) => {
  return dayjs(dateString).format('YYYY-MM-DD HH:mm:ss')
}

onMounted(() => {
  loadReports()
})
</script>

<style scoped>
.report-view {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h3 {
  margin: 0;
  color: #303133;
}

.content {
  flex: 1;
  overflow: auto;
}

.step-collapse-title {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.step-title-text {
  flex: 1;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-method-tag {
  display: inline-block;
  padding: 0 6px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 3px;
  background: #eef2ff;
  color: #5046e5;
  margin-left: 6px;
}

.step-attempt {
  font-size: 12px;
  color: #e6a23c;
}

.step-detail-body {
  padding: 12px 0;
}

.step-summary-row {
  display: flex;
  gap: 24px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.step-summary-item {
  font-size: 13px;
  color: #606266;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.step-tabs {
  margin-top: 8px;
}

.assertion-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 13px;
  margin-bottom: 4px;
}

.assertion-line.is-passed {
  background: #f0f9eb;
  color: #67c23a;
}

.assertion-line.is-failed {
  background: #fef0f0;
  color: #f56c6c;
}

.assertion-status {
  font-weight: bold;
  width: 16px;
}

.assertion-name {
  flex: 1;
  color: #303133;
}

.assertion-error {
  color: #f56c6c;
  font-size: 12px;
}

.extracted-var-line {
  padding: 4px 10px;
  font-size: 13px;
  display: flex;
  gap: 8px;
  border-bottom: 1px dashed #ebeef5;
}

.var-key {
  color: #5046e5;
  font-weight: 500;
}

.var-value {
  flex: 1;
  color: #303133;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  word-break: break-all;
}

.script-log-pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  font-family: 'SFMono-Regular', Consolas, monospace;
  max-height: 360px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.script-log-pre.error-pre {
  background: #fef0f0;
  color: #f56c6c;
}
</style>
