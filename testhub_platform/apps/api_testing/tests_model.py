"""api_testing 应用 model 层烟雾测试。

注:引擎/工具层单元测试在 tests.py(88 个,已存在),本文件只补 model 层覆盖。
P0 数据隔离(TestDataset)已由 tests.py::TestDatasetViewSetTest::test_queryset_isolation
覆盖,此处不重复。

重点验证:
  - ApiProject 成员可见性(原 tests.py 未覆盖)
  - ScheduledTask.update_run_stats(P1 原子自增,原 tests.py 未覆盖)
  - TestSuiteRequest 唯一约束(原 tests.py 只用作 setup,未显式验证唯一性)
"""
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.api_testing.models import (
    ApiProject, TestDataset, TestSuite, TestSuiteRequest,
    ApiRequest, ScheduledTask, ApiCollection,
)


class ApiProjectAccessTest(DjangoTestCase):
    """ApiProject 数据隔离:owner 和 member 可见,outsider 不可见。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.member = User.objects.create_user(username='member', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = ApiProject.objects.create(
            name='P', project_type='HTTP', status='NOT_STARTED', owner=self.owner,
        )
        self.project.members.add(self.member)

    def test_owner_listed(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/api-testing/projects/')
        self.assertEqual(resp.status_code, 200)
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertIn(self.project.id, ids)

    def test_member_listed(self):
        c = APIClient()
        c.force_authenticate(user=self.member)
        resp = c.get('/api/api-testing/projects/')
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertIn(self.project.id, ids)

    def test_outsider_not_listed(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/api-testing/projects/')
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertNotIn(self.project.id, ids)


class ScheduledTaskStatsTest(DjangoTestCase):
    """P1 修复验证:ScheduledTask.update_run_stats 原子更新计数。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.task = ScheduledTask.objects.create(
            name='scheduled',
            task_type='TEST_SUITE',
            trigger_type='ONCE',
            created_by=self.owner,
        )

    def test_update_run_stats_success(self):
        self.task.update_run_stats(success=True)
        self.task.refresh_from_db()
        self.assertEqual(self.task.total_runs, 1)
        self.assertEqual(self.task.successful_runs, 1)

    def test_update_run_stats_failure(self):
        self.task.update_run_stats(success=False)
        self.task.refresh_from_db()
        self.assertEqual(self.task.failed_runs, 1)
        self.assertEqual(self.task.successful_runs, 0)

    def test_update_run_stats_multiple(self):
        for _ in range(5):
            self.task.update_run_stats(success=True)
        self.task.refresh_from_db()
        self.assertEqual(self.task.total_runs, 5)


class TestSuiteRequestUniqueTest(DjangoTestCase):
    """唯一约束:test_suite + request 不能重复。"""

    def test_unique_suite_request(self):
        owner = User.objects.create_user(username='u', password='x')
        project = ApiProject.objects.create(
            name='P', project_type='HTTP', status='NOT_STARTED', owner=owner,
        )
        collection = ApiCollection.objects.create(
            name='C', project=project,
        )
        req = ApiRequest.objects.create(
            collection=collection, name='R', method='GET', url='/api/x',
            created_by=owner,
        )
        suite = TestSuite.objects.create(
            name='S', project=project, created_by=owner,
        )
        TestSuiteRequest.objects.create(test_suite=suite, request=req, order=1)
        with self.assertRaises(Exception):
            TestSuiteRequest.objects.create(test_suite=suite, request=req, order=2)
