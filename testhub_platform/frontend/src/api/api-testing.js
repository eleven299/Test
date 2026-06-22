import request from '@/utils/api'

// 仪表盘相关API
export function getDashboardStats() {
  return request({
    url: '/api-testing/dashboard/stats/',
    method: 'get'
  })
}

// 获取定时任务列表
export function getScheduledTasks(params) {
  return request({
    url: '/api-testing/scheduled-tasks/',
    method: 'get',
    params
  })
}

// 创建定时任务
export function createScheduledTask(data) {
  return request({
    url: '/api-testing/scheduled-tasks/',
    method: 'post',
    data
  })
}

// 更新定时任务
export function updateScheduledTask(id, data) {
  return request({
    url: `/api-testing/scheduled-tasks/${id}/`,
    method: 'patch',
    data
  })
}

// 删除定时任务
export function deleteScheduledTask(id) {
  return request({
    url: `/api-testing/scheduled-tasks/${id}/`,
    method: 'delete'
  })
}

// 立即执行定时任务
export function runScheduledTask(id) {
  return request({
    url: `/api-testing/scheduled-tasks/${id}/run_now/`,
    method: 'post'
  })
}

// 获取执行日志
export function getExecutionLogs(taskId, params = {}) {
  return request({
    url: `/api-testing/scheduled-tasks/${taskId}/execution_logs/`,
    method: 'get',
    params
  })
}

// 获取测试套件列表
export function getTestSuites(params) {
  return request({
    url: '/api-testing/test-suites/',
    method: 'get',
    params
  })
}

// 获取API请求列表
export function getApiRequests(params) {
  return request({
    url: '/api-testing/requests/',
    method: 'get',
    params
  })
}

// 获取环境列表
export function getEnvironments(params) {
  return request({
    url: '/api-testing/environments/',
    method: 'get',
    params
  })
}

// 获取项目列表
export function getApiProjects(params) {
  return request({
    url: '/api-testing/projects/',
    method: 'get',
    params
  })
}

// 获取集合列表
export function getApiCollections(params) {
  return request({
    url: '/api-testing/collections/',
    method: 'get',
    params
  })
}

// 执行测试套件
export function executeTestSuite(id, data) {
  return request({
    url: `/api-testing/test-suites/${id}/execute/`,
    method: 'post',
    data
  })
}

// 执行API请求
export function executeApiRequest(id, data) {
  return request({
    url: `/api-testing/api-requests/${id}/execute/`,
    method: 'post',
    data
  })
}

// 获取执行结果
export function getExecutionResult(id) {
  return request({
    url: `/api-testing/executions/${id}/`,
    method: 'get'
  })
}

// 获取请求历史
export function getRequestHistory(params) {
  return request({
    url: '/api-testing/histories/',
    method: 'get',
    params
  })
}

// 删除请求历史
export function deleteRequestHistory(id) {
  return request({
    url: `/api-testing/histories/${id}/`,
    method: 'delete'
  })
}

// 批量删除请求历史
export function batchDeleteRequestHistory(ids) {
  return request({
    url: '/api-testing/histories/batch-delete/',
    method: 'post',
    data: { ids }
  })
}

// 获取用户列表
export function getUsers(params) {
  return request({
    url: '/api-testing/users/',
    method: 'get',
    params
  })
}
// 获取操作日志
export function getOperationLogs(params) {
  return request({
    url: '/api-testing/operation-logs/',
    method: 'get',
    params
  })
}

// ================ 测试数据集 (DDT) ================

export function getDatasets(params) {
  return request({
    url: '/api-testing/datasets/',
    method: 'get',
    params
  })
}

export function getDataset(id) {
  return request({
    url: `/api-testing/datasets/${id}/`,
    method: 'get'
  })
}

export function createDataset(data) {
  return request({
    url: '/api-testing/datasets/',
    method: 'post',
    data
  })
}

export function updateDataset(id, data) {
  return request({
    url: `/api-testing/datasets/${id}/`,
    method: 'patch',
    data
  })
}

export function deleteDataset(id) {
  return request({
    url: `/api-testing/datasets/${id}/`,
    method: 'delete'
  })
}

export function batchDeleteDatasets(ids) {
  return request({
    url: '/api-testing/datasets/bulk-delete/',
    method: 'post',
    data: { ids }
  })
}

export function importDatasetCsv(id, file, hasHeader = true, encoding = 'utf-8') {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('has_header', String(hasHeader))
  formData.append('encoding', encoding)
  return request({
    url: `/api-testing/datasets/${id}/import-csv/`,
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  })
}

// 用数据集驱动一次测试套件执行(DDT 批量执行)
export function runDataset(id, data) {
  return request({
    url: `/api-testing/datasets/${id}/run/`,
    method: 'post',
    data
  })
}

// 获取测试套件的简练列表(只含 id/name/project,用于批量执行对话框)
export function getTestSuitesLite(params) {
  return request({
    url: '/api-testing/test-suites/',
    method: 'get',
    params
  })
}

// 导出测试执行报告(fmt: 'json' | 'junit';download=true 触发文件下载)
// 注意:不用 ?format= 作为 query param 名,DRF 会把它当作 format suffix 处理,
// junit 没有对应 renderer 会被内容协商拦截返回 404。
export function buildExportReportUrl(executionId, format, download = true, includeSnapshots = true) {
  const params = new URLSearchParams()
  params.set('fmt', format)
  params.set('download', download ? '1' : '0')
  if (format === 'json') {
    params.set('include_snapshots', includeSnapshots ? '1' : '0')
  }
  return `/api-testing/test-executions/${executionId}/export-report/?${params.toString()}`
}
