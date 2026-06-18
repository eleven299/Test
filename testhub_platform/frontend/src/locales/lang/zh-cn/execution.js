export default {
  // Page titles
  title: '执行记录',
  testPlan: '测试计划',
  planDetail: '计划详情',
  executionHistory: '执行历史记录',
  inDevelopment: '执行记录功能开发中...',

  // Actions
  newPlan: '新建测试计划',
  batchDelete: '批量删除',
  viewExecution: '查看执行',
  createPlan: '创建',
  updatePlan: '保存',
  closePlan: '关闭',
  activatePlan: '激活',
  viewHistory: '历史',

  // Templates
  createFromTemplate: '从模板创建',
  templateAppTwoWeek: 'App 两周迭代',
  templateAppTwoWeekName: '【App两周迭代】{version} 测试计划',
  templateAppTwoWeekDesc: `【迭代周期】两周（D1-D14）

【阶段安排】
• D1（周一）  需求评审、迭代排期、测试范围圈定
• D2-D3      测试用例设计、用例评审、接口联调
• D4-D5      第一轮功能测试（冒烟+主流程+异常场景）
• D6         接口测试、性能基准测试
• D7         兼容性测试（多机型/多系统版本/分辨率）
• D8-D9      第二轮功能测试（边界/中断/弱网/权限）
• D10        缺陷修复验证、第三轮回归测试
• D11        升级兼容测试、安装/卸载/覆盖安装
• D12        验收测试（UAT）、UI走查
• D13        预发环境验证、上线 Checklist 准备
• D14        灰度发布、线上监控、应急预案

【测试范围】
1. 功能测试    主流程、二级页面、状态切换
2. 接口测试    异常码、超时重试、参数校验
3. 兼容性测试  iOS/Android 主流机型 × 系统版本
4. 性能测试    启动时间、内存、CPU、FPS、流量
5. 弱网/中断   2G/3G/4G/WiFi 切换、断网重连、来电中断
6. 升级兼容    老版本升级、数据迁移、回滚验证
7. 安全测试    越权、敏感信息脱敏、抓包防护

【环境要求】
• 开发环境 D1-D3
• 测试环境 D4-D11
• 预发环境 D12-D13
• 灰度/生产 D14

【准入/准出标准】
• 准入：需求评审完成、设计稿定稿、提测单已发
• 准出：P0/P1 缺陷 100% 修复、P2 修复率 ≥ 90%、回归通过、性能达标`,

  // Table columns
  serialNumber: '序号',
  planName: '计划名称',
  project: '项目',
  projects: '项目',
  version: '版本',
  creator: '创建者',
  status: '状态',
  createdAt: '创建时间',
  actions: '操作',
  testCase: '测试用例',
  executionStatus: '执行状态',
  comments: '备注',
  executedBy: '执行者',
  executedAt: '执行时间',

  // Status
  active: '激活',
  closed: '已关闭',
  untested: '未测试',
  passed: '通过',
  failed: '失败',
  blocked: '阻塞',
  retest: '重测',
  completed: '已完成',
  notStarted: '未开始',
  inProgress: '进行中',

  // Statistics
  total: '总计',
  progressRate: '进度',

  // Dialog titles
  createPlanDialog: '新建测试计划',
  editPlanDialog: '编辑测试计划',

  // Form labels
  planDescription: '计划描述',
  relatedProjects: '关联项目',
  relatedVersion: '关联版本',
  testCases: '测试用例',
  assignees: '指派给',
  planStatus: '状态',
  activeText: '激活',
  inactiveText: '已关闭',

  // Placeholders
  planNamePlaceholder: '请输入计划名称',
  planDescriptionPlaceholder: '请输入计划描述',
  selectProjects: '请选择项目',
  selectVersion: '请选择版本',
  selectTestcases: '请选择用例',
  selectTestcasesDisabled: '请先选择项目',
  selectTestcasesButton: '请选择测试用例',
  modifyTestcasesSelection: '修改选择',
  selectedTestcasesCount: '已选择{count}条测试用例',
  noTestcasesSelected: '暂无已选用例',
  loadingTestcases: '加载中...',
  selectAssignees: '请选择执行人员',
  commentsPlaceholder: '请输入备注',
  testcaseSelectorTitle: '选择测试用例',
  testcaseKeyword: '关键词',
  testcaseKeywordPlaceholder: '按标题搜索',
  testcasePriority: '优先级',
  testcaseType: '测试类型',
  allPriorities: '全部优先级',
  allTypes: '全部类型',
  testcaseCode: '编号',
  testcaseTitle: '标题',
  testcaseProject: '所属项目',
  resetSearch: '重置',
  confirmSelectTestcases: '确认选择({count})',

  // Filters
  selectProject: '选择项目',
  selectStatus: '选择状态',
  filterActive: '激活',
  filterClosed: '已关闭',

  // Messages
  fetchListFailed: '获取测试计划失败',
  fetchDetailFailed: '获取测试计划详情失败',
  fetchBasicDataFailed: '获取基础数据失败',
  fetchTestcasesFailed: '获取测试用例失败',
  fetchHistoryFailed: '获取历史记录失败',
  createSuccess: '测试计划创建成功',
  createFailed: '创建测试计划失败',
  updateSuccess: '测试计划更新成功',
  updateFailed: '更新测试计划失败',
  statusUpdateSuccess: '状态更新成功',
  statusUpdateFailed: '状态更新失败',
  detailsUpdateSuccess: '详细信息更新成功',
  detailsUpdateFailed: '详细信息更新失败',
  selectFirst: '请先选择要删除的测试计划',
  selectCasesFirst: '请先选择要删除的用例',
  selectProjectFirst: '请先选择项目',
  selectProjectBeforeOpenTestcases: '请先选择关联项目，再选择测试用例',
  batchDeleteConfirm: '确定要删除选中的 {count} 个测试计划吗？此操作不可恢复。',
  batchDeleteCasesConfirm: '确定要删除选中的 {count} 个用例吗？此操作不可恢复。',
  batchDeleteSuccess: '成功删除 {successCount} 个测试计划',
  batchDeleteCasesSuccess: '成功删除 {successCount} 个用例',
  batchDeletePartialSuccess: '成功删除 {successCount} 个测试计划，{failCount} 个失败',
  batchDeleteCasesPartialSuccess: '成功删除 {successCount} 个用例，{failCount} 个失败',
  batchDeleteFailed: '删除失败',
  toggleStatusConfirm: '确定要{action}这个测试计划吗？',
  toggleStatusSuccess: '{action}成功',
  toggleStatusFailed: '操作失败',

  // Other
  noProject: '未关联项目',
  noData: '-',

  // Validation
  planNameRequired: '请输入计划名称',
  projectsRequired: '请选择项目',
  testcasesRequired: '请选择至少一个测试用例',
  selectProjectBeforeTestcases: '请先选择项目'
}
