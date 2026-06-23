"""reports 应用烟雾测试。"""
from django.test import TestCase as DjangoTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import User
from apps.projects.models import Project
from apps.executions.models import TestPlan, TestRun, TestRunCase
from apps.testcases.models import TestCase
from apps.reports.models import TestReport, ReportTemplate


class ReportModelTest(DjangoTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)
        self.plan = TestPlan.objects.create(name='Plan', creator=self.owner)
        self.run = TestRun.objects.create(
            name='R', test_plan=self.plan, project=self.project,
            assignee=self.owner, creator=self.owner,
        )

    def test_create_report_defaults(self):
        report = TestReport.objects.create(
            project=self.project, name='R1', generated_by=self.owner
        )
        self.assertEqual(report.report_type, 'execution')
        self.assertEqual(report.summary, {})
        self.assertEqual(report.content, {})

    def test_create_report_with_execution(self):
        report = TestReport.objects.create(
            project=self.project, name='R2',
            report_type='summary', execution=self.run,
            summary={'pass': 10}, generated_by=self.owner,
        )
        self.assertEqual(report.execution, self.run)
        self.assertEqual(report.summary['pass'], 10)
        # OneToOne 反向
        self.assertEqual(self.run.report, report)

    def test_report_ordering(self):
        TestReport.objects.create(project=self.project, name='A', generated_by=self.owner)
        TestReport.objects.create(project=self.project, name='B', generated_by=self.owner)
        names = [r.name for r in TestReport.objects.all()]
        # ordering = ['-created_at'], B 后创建所以排前面
        self.assertEqual(names, ['B', 'A'])


class ReportTemplateModelTest(DjangoTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')

    def test_create_template_defaults(self):
        tpl = ReportTemplate.objects.create(name='T1', created_by=self.owner)
        self.assertFalse(tpl.is_default)
        self.assertEqual(tpl.template_config, {})


class ReportEndpointSmokeTest(DjangoTestCase):
    """P0 数据隔离 + 端点可用性:所有报告统计接口仅返回当前用户可访问项目的数据。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)
        self.plan = TestPlan.objects.create(name='Plan', creator=self.owner)
        self.plan.projects.add(self.project)
        self.run = TestRun.objects.create(
            name='R', test_plan=self.plan, project=self.project,
            assignee=self.owner, creator=self.owner,
        )
        self.case = TestCase.objects.create(
            title='TC', project=self.project, expected_result='pass',
            author=self.owner,
        )
        self.run_case = TestRunCase.objects.create(
            test_run=self.run, testcase=self.case,
            status='failed', priority='high',
            executed_by=self.owner,
            executed_at=timezone.now(),
            defects=['BUG-1', 'BUG-2'],
        )

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_dashboard_owner(self):
        resp = self._client(self.owner).get('/api/reports/reports/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['active_plans'], 1)
        # failed 用例带 2 条缺陷
        self.assertEqual(resp.data['total_defects'], 2)

    def test_dashboard_outsider_sees_nothing(self):
        """P0:outsider 看不到 owner 项目的数据。"""
        resp = self._client(self.outsider).get('/api/reports/reports/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['active_plans'], 0)
        self.assertEqual(resp.data['total_defects'], 0)

    def test_dashboard_unknown_project_404(self):
        """P0:project 参数必须是当前用户可访问的项目,否则 404。"""
        resp = self._client(self.outsider).get(
            f'/api/reports/reports/dashboard/?project={self.project.id}'
        )
        self.assertEqual(resp.status_code, 404)

    def test_status_distribution_owner(self):
        resp = self._client(self.owner).get('/api/reports/reports/status_distribution/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['failed'], 1)
        # STATUS_CHOICES 中未出现的键补 0
        for key in ('untested', 'passed', 'failed', 'blocked', 'retest'):
            self.assertIn(key, resp.data)

    def test_status_distribution_outsider_isolated(self):
        resp = self._client(self.outsider).get('/api/reports/reports/status_distribution/')
        self.assertEqual(resp.data['failed'], 0)

    def test_defect_distribution_owner(self):
        resp = self._client(self.owner).get('/api/reports/reports/defect_distribution/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['value'], 1)

    def test_failed_cases_top_owner(self):
        resp = self._client(self.owner).get('/api/reports/reports/failed_cases_top/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['testcase__title'], 'TC')

    def test_execution_trend_owner(self):
        """默认 7 天窗口,长度必须等于 7。"""
        resp = self._client(self.owner).get('/api/reports/reports/execution_trend/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 7)
        # 今日应有 1 条
        today_entry = resp.data[-1]
        self.assertEqual(today_entry['count'], 1)

    def test_execution_trend_custom_days(self):
        resp = self._client(self.owner).get('/api/reports/reports/execution_trend/?days=3')
        self.assertEqual(len(resp.data), 3)

    def test_ai_efficiency_owner(self):
        resp = self._client(self.owner).get('/api/reports/reports/ai_efficiency/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('ai_vs_manual', resp.data)
        self.assertIn('adoption_rate', resp.data)
        self.assertIn('saved_hours', resp.data)

    def test_team_workload_owner(self):
        resp = self._client(self.owner).get('/api/reports/reports/team_workload/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['username'], 'owner')
        self.assertEqual(resp.data[0]['execution_count'], 1)
        # failed 用例算作缺陷
        self.assertEqual(resp.data[0]['defect_count'], 1)

    def test_team_workload_outsider_empty(self):
        resp = self._client(self.outsider).get('/api/reports/reports/team_workload/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])
