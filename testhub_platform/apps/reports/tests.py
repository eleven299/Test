"""reports 应用烟雾测试。"""
from django.test import TestCase as DjangoTestCase

from apps.users.models import User
from apps.projects.models import Project
from apps.executions.models import TestPlan, TestRun
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
