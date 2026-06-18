export default {
  // Page titles
  title: 'Execution Records',
  testPlan: 'Test Plan',
  planDetail: 'Plan Details',
  executionHistory: 'Execution History',
  inDevelopment: 'Execution records feature under development...',

  // Actions
  newPlan: 'New Test Plan',
  batchDelete: 'Batch Delete',
  viewExecution: 'View Execution',
  createPlan: 'Create',
  updatePlan: 'Save',
  closePlan: 'Close',
  activatePlan: 'Activate',
  viewHistory: 'History',

  // Templates
  createFromTemplate: 'Create from Template',
  templateAppTwoWeek: 'App 2-Week Iteration',
  templateAppTwoWeekName: '[App 2-Week Iteration] {version} Test Plan',
  templateAppTwoWeekDesc: `Iteration Cycle: 2 weeks (D1-D14)

Phase Schedule
• D1 (Mon)    Requirement review, iteration planning, scope definition
• D2-D3       Test case design, case review, API integration
• D4-D5       Round 1 functional testing (smoke + main flow + edge cases)
• D6          API testing, performance baseline
• D7          Compatibility testing (devices x OS versions x resolutions)
• D8-D9       Round 2 functional testing (boundary/interruption/weak-network/permission)
• D10         Bug fix verification, Round 3 regression
• D11         Upgrade compatibility, install/uninstall/overlay install
• D12         UAT, UI walkthrough
• D13         Pre-release verification, release checklist
• D14         Canary release, online monitoring, contingency plan

Test Scope
1. Functional    Main flow, secondary pages, state transitions
2. API           Error codes, timeout retry, param validation
3. Compatibility iOS/Android mainstream devices x OS versions
4. Performance   Cold start, memory, CPU, FPS, traffic
5. Weak-network  2G/3G/4G/WiFi switching, reconnect, call interrupt
6. Upgrade       Old version upgrade, data migration, rollback
7. Security      Privilege escalation, PII masking, anti-capture

Environment
• Dev           D1-D3
• Test          D4-D11
• Pre-release   D12-D13
• Canary/Prod   D14

Entry / Exit Criteria
• Entry: requirement reviewed, design frozen, handoff ticket issued
• Exit: P0/P1 100% fixed, P2 fix rate >= 90%, regression passed, performance meets target`,

  // Table columns
  serialNumber: 'No.',
  planName: 'Plan Name',
  project: 'Project',
  projects: 'Projects',
  version: 'Version',
  creator: 'Creator',
  status: 'Status',
  createdAt: 'Created At',
  actions: 'Actions',
  testCase: 'Test Case',
  executionStatus: 'Execution Status',
  comments: 'Comments',
  executedBy: 'Executed By',
  executedAt: 'Executed At',

  // Status
  active: 'Active',
  closed: 'Closed',
  untested: 'Untested',
  passed: 'Passed',
  failed: 'Failed',
  blocked: 'Blocked',
  retest: 'Retest',
  completed: 'Completed',
  notStarted: 'Not Started',
  inProgress: 'In Progress',

  // Statistics
  total: 'Total',
  progressRate: 'Progress',

  // Dialog titles
  createPlanDialog: 'New Test Plan',
  editPlanDialog: 'Edit Test Plan',

  // Form labels
  planDescription: 'Plan Description',
  relatedProjects: 'Related Projects',
  relatedVersion: 'Related Version',
  testCases: 'Test Cases',
  assignees: 'Assignees',
  planStatus: 'Status',
  activeText: 'Active',
  inactiveText: 'Closed',

  // Placeholders
  planNamePlaceholder: 'Enter plan name',
  planDescriptionPlaceholder: 'Enter plan description',
  selectProjects: 'Select projects',
  selectVersion: 'Select version',
  selectTestcases: 'Select test cases',
  selectTestcasesDisabled: 'Please select project first',
  selectTestcasesButton: 'Select Test Cases',
  modifyTestcasesSelection: 'Modify Selection',
  selectedTestcasesCount: '{count} test cases selected',
  noTestcasesSelected: 'No test cases selected',
  loadingTestcases: 'Loading...',
  selectAssignees: 'Select assignees',
  commentsPlaceholder: 'Enter comments',
  testcaseSelectorTitle: 'Select Test Cases',
  testcaseKeyword: 'Keyword',
  testcaseKeywordPlaceholder: 'Search by title',
  testcasePriority: 'Priority',
  testcaseType: 'Test Type',
  allPriorities: 'All Priorities',
  allTypes: 'All Types',
  testcaseCode: 'ID',
  testcaseTitle: 'Title',
  testcaseProject: 'Project',
  resetSearch: 'Reset',
  confirmSelectTestcases: 'Confirm ({count})',

  // Filters
  selectProject: 'Select Project',
  selectStatus: 'Select Status',
  filterActive: 'Active',
  filterClosed: 'Closed',

  // Messages
  fetchListFailed: 'Failed to fetch test plans',
  fetchDetailFailed: 'Failed to fetch test plan details',
  fetchBasicDataFailed: 'Failed to fetch basic data',
  fetchTestcasesFailed: 'Failed to fetch test cases',
  fetchHistoryFailed: 'Failed to fetch execution history',
  createSuccess: 'Test plan created successfully',
  createFailed: 'Failed to create test plan',
  updateSuccess: 'Test plan updated successfully',
  updateFailed: 'Failed to update test plan',
  statusUpdateSuccess: 'Status updated successfully',
  statusUpdateFailed: 'Failed to update status',
  detailsUpdateSuccess: 'Details updated successfully',
  detailsUpdateFailed: 'Failed to update details',
  selectFirst: 'Please select test plans to delete first',
  selectCasesFirst: 'Please select cases to delete first',
  selectProjectFirst: 'Please select project first',
  selectProjectBeforeOpenTestcases: 'Please select related project(s) before selecting test cases',
  batchDeleteConfirm: 'Are you sure to delete selected {count} test plans? This action cannot be undone.',
  batchDeleteCasesConfirm: 'Are you sure to delete selected {count} cases? This action cannot be undone.',
  batchDeleteSuccess: 'Successfully deleted {successCount} test plans',
  batchDeleteCasesSuccess: 'Successfully deleted {successCount} cases',
  batchDeletePartialSuccess: 'Successfully deleted {successCount} test plans, {failCount} failed',
  batchDeleteCasesPartialSuccess: 'Successfully deleted {successCount} cases, {failCount} failed',
  batchDeleteFailed: 'Delete failed',
  toggleStatusConfirm: 'Are you sure to {action} this test plan?',
  toggleStatusSuccess: '{action} successful',
  toggleStatusFailed: 'Operation failed',

  // Other
  noProject: 'No Project',
  noData: '-',

  // Validation
  planNameRequired: 'Please enter plan name',
  projectsRequired: 'Please select project',
  testcasesRequired: 'Please select at least one test case',
  selectProjectBeforeTestcases: 'Please select project first'
}
