"""executions 应用烟雾测试。

重点验证:
  - TestPlan / TestRun / TestRunCase 基本创建
  - TestRun.bulk_progress_stats(P3 性能修复):一条 SQL 算多个 run
  - TestRunViewSet 数据隔离(P0):不可访问项目下的 run 不应返回
  - TestRunCaseViewSet.update_status 状态变更 + 历史记录
"""
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.projects.models import Project
from apps.testcases.models import TestCase as TestCaseModel
from apps.executions.models import TestPlan, TestRun, TestRunCase, TestRunCaseHistory


class ExecutionModelTest(DjangoTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)
        self.case = TestCaseModel.objects.create(
            project=self.project, title='T', expected_result='ok', author=self.owner
        )

    def test_create_plan_and_run(self):
        plan = TestPlan.objects.create(name='P1', creator=self.owner)
        plan.projects.add(self.project)
        run = TestRun.objects.create(
            name='R1', test_plan=plan, project=self.project, assignee=self.owner, creator=self.owner
        )
        self.assertEqual(run.status, 'untested')

    def test_bulk_progress_stats_empty(self):
        stats = TestRun.bulk_progress_stats([])
        self.assertEqual(stats, {})

    def test_bulk_progress_stats_aggregates(self):
        plan = TestPlan.objects.create(name='P1', creator=self.owner)
        run1 = TestRun.objects.create(
            name='R1', test_plan=plan, project=self.project, assignee=self.owner, creator=self.owner
        )
        run2 = TestRun.objects.create(
            name='R2', test_plan=plan, project=self.project, assignee=self.owner, creator=self.owner
        )
        # 用两条不同 testcase 避开 unique_together=['test_run','testcase']
        case_a = TestCaseModel.objects.create(
            project=self.project, title='A', expected_result='ok', author=self.owner
        )
        case_b = TestCaseModel.objects.create(
            project=self.project, title='B', expected_result='ok', author=self.owner
        )
        TestRunCase.objects.create(test_run=run1, testcase=case_a, status='passed')
        TestRunCase.objects.create(test_run=run1, testcase=case_b, status='failed')
        TestRunCase.objects.create(test_run=run2, testcase=case_a, status='passed')

        stats = TestRun.bulk_progress_stats([run1.id, run2.id])
        # run1: 1 passed + 1 failed -> progress 100%
        self.assertEqual(stats[run1.id]['passed'], 1)
        self.assertEqual(stats[run1.id]['failed'], 1)
        self.assertEqual(stats[run1.id]['progress'], 100.0)
        # run2: 1 passed, 1 total -> progress 100%
        self.assertEqual(stats[run2.id]['passed'], 1)
        self.assertEqual(stats[run2.id]['total'], 1)
        self.assertEqual(stats[run2.id]['progress'], 100.0)

    def test_bulk_progress_stats_handles_untested(self):
        plan = TestPlan.objects.create(name='P1', creator=self.owner)
        run = TestRun.objects.create(
            name='R', test_plan=plan, project=self.project, assignee=self.owner, creator=self.owner
        )
        TestRunCase.objects.create(test_run=run, testcase=self.case, status='untested')
        stats = TestRun.bulk_progress_stats([run.id])
        self.assertEqual(stats[run.id]['progress'], 0.0)
        self.assertEqual(stats[run.id]['untested'], 1)


class TestRunAccessTest(DjangoTestCase):
    """P0 数据隔离:outsider 看不到不可访问项目下的 TestRun。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='out', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)
        plan = TestPlan.objects.create(name='Plan', creator=self.owner)
        plan.projects.add(self.project)
        self.run = TestRun.objects.create(
            name='R', test_plan=plan, project=self.project,
            assignee=self.owner, creator=self.owner,
        )

    def test_owner_lists_run(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/executions/runs/')
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data.get('results', resp.data)]
        self.assertIn(self.run.id, ids)

    def test_outsider_does_not_list_run(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/executions/runs/')
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data.get('results', resp.data)]
        self.assertNotIn(self.run.id, ids)


class UpdateStatusActionTest(DjangoTestCase):
    """update_status 应同时:更新 TestRunCase 状态 + 写入 TestRunCaseHistory。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)
        self.case = TestCaseModel.objects.create(
            project=self.project, title='T', expected_result='ok', author=self.owner
        )
        plan = TestPlan.objects.create(name='Plan', creator=self.owner)
        plan.projects.add(self.project)
        self.run = TestRun.objects.create(
            name='R', test_plan=plan, project=self.project,
            assignee=self.owner, creator=self.owner,
        )
        self.run_case = TestRunCase.objects.create(
            test_run=self.run, testcase=self.case, status='untested',
        )

    def test_update_status_changes_state(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.patch(
            f'/api/executions/run_cases/{self.run_case.id}/update_status/',
            {'status': 'passed', 'actual_result': '通过'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.run_case.refresh_from_db()
        self.assertEqual(self.run_case.status, 'passed')
        self.assertEqual(self.run_case.actual_result, '通过')
        self.assertIsNotNone(self.run_case.executed_at)

    def test_update_status_creates_history(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        c.patch(
            f'/api/executions/run_cases/{self.run_case.id}/update_status/',
            {'status': 'failed', 'comments': '失败原因'},
            format='json',
        )
        self.assertEqual(TestRunCaseHistory.objects.count(), 1)
        history = TestRunCaseHistory.objects.first()
        self.assertEqual(history.status, 'failed')
        self.assertEqual(history.comments, '失败原因')
        self.assertEqual(history.executed_by, self.owner)

    def test_update_status_requires_status_field(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.patch(
            f'/api/executions/run_cases/{self.run_case.id}/update_status/',
            {'actual_result': '无状态'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_history_endpoint_returns_records(self):
        # 先创建一条历史
        TestRunCaseHistory.objects.create(
            run_case=self.run_case, status='passed',
            executed_by=self.owner,
        )
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get(f'/api/executions/run_cases/{self.run_case.id}/history/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['status'], 'passed')
