"""ui_automation 应用 view 层烟雾测试。

model 层在 tests.py(6 个)。本文件覆盖 view 层关键端点,重点验证:
  - UiProjectViewSet:owner/member 可见,outsider 不可见
  - ElementViewSet:通过可访问项目过滤
  - UiScheduledTaskViewSet:数据隔离 + pause/resume 状态变更
  - TestSuiteViewSet / TestCaseViewSet:数据隔离(accessible projects)
  - AIExecutionRecordViewSet:数据隔离 + batch_delete 校验
"""
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.ui_automation.models import (
    UiProject, LocatorStrategy, Element, UiScheduledTask,
    TestSuite, TestCase as UiTestCase, AIExecutionRecord,
)


class UiProjectViewSetAccessTest(DjangoTestCase):
    """P0 数据隔离:owner / member 可见,outsider 不可见。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.member = User.objects.create_user(username='member', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = UiProject.objects.create(
            name='P', base_url='https://example.com', owner=self.owner,
        )
        self.project.members.add(self.member)

    def test_owner_sees_project(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/ui-automation/projects/')
        self.assertEqual(resp.status_code, 200)
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertIn(self.project.id, ids)

    def test_member_sees_project(self):
        c = APIClient()
        c.force_authenticate(user=self.member)
        resp = c.get('/api/ui-automation/projects/')
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertIn(self.project.id, ids)

    def test_outsider_does_not_see_project(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/ui-automation/projects/')
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertNotIn(self.project.id, ids)


class ElementViewSetAccessTest(DjangoTestCase):
    """P0 数据隔离:Element 跟随 project 可见性,outsider 不可见。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = UiProject.objects.create(
            name='P', base_url='https://example.com', owner=self.owner,
        )
        self.strategy = LocatorStrategy.objects.create(name='css')
        self.element = Element.objects.create(
            project=self.project, locator_strategy=self.strategy,
            name='login-btn', locator_value='.btn-login',
            created_by=self.owner,
        )

    def test_owner_sees_element(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/ui-automation/elements/')
        self.assertEqual(resp.status_code, 200)
        ids = [e['id'] for e in resp.data.get('results', resp.data)]
        self.assertIn(self.element.id, ids)

    def test_outsider_does_not_see_element(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/ui-automation/elements/')
        ids = [e['id'] for e in resp.data.get('results', resp.data)]
        self.assertNotIn(self.element.id, ids)

    def test_tree_rejects_missing_project(self):
        """tree action 必须传 project 参数。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/ui-automation/elements/tree/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('项目', resp.data['error'])


class UiScheduledTaskViewSetTest(DjangoTestCase):
    """P0 数据隔离 + 状态变更:
      - outsider 看不到 owner 项目下的定时任务
      - pause/resume 切换状态
    """

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = UiProject.objects.create(
            name='P', base_url='https://example.com', owner=self.owner,
        )
        self.task = UiScheduledTask.objects.create(
            name='T', task_type='TEST_SUITE', trigger_type='ONCE',
            project=self.project, created_by=self.owner, status='ACTIVE',
        )

    def test_owner_lists_task(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/ui-automation/scheduled-tasks/')
        self.assertEqual(resp.status_code, 200)
        ids = [t['id'] for t in resp.data.get('results', resp.data)]
        self.assertIn(self.task.id, ids)

    def test_outsider_does_not_see_task(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/ui-automation/scheduled-tasks/')
        ids = [t['id'] for t in resp.data.get('results', resp.data)]
        self.assertNotIn(self.task.id, ids)

    def test_pause_changes_status(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(f'/api/ui-automation/scheduled-tasks/{self.task.id}/pause/')
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'PAUSED')

    def test_resume_changes_status_back(self):
        # 先 pause 再 resume
        c = APIClient()
        c.force_authenticate(user=self.owner)
        c.post(f'/api/ui-automation/scheduled-tasks/{self.task.id}/pause/')
        resp = c.post(f'/api/ui-automation/scheduled-tasks/{self.task.id}/resume/')
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'ACTIVE')

    def test_outsider_cannot_pause_task(self):
        """outsider 通过 URL 直接访问 task,因 get_queryset 过滤会 404。"""
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.post(f'/api/ui-automation/scheduled-tasks/{self.task.id}/pause/')
        self.assertEqual(resp.status_code, 404)
        # task 状态未变
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'ACTIVE')


class TestSuiteViewSetAccessTest(DjangoTestCase):
    """P0 数据隔离:TestSuite 跟随 project 可见性。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = UiProject.objects.create(
            name='P', base_url='https://example.com', owner=self.owner,
        )
        self.suite = TestSuite.objects.create(
            project=self.project, name='S',
        )

    def test_owner_sees_suite(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/ui-automation/test-suites/')
        self.assertEqual(resp.status_code, 200)
        ids = [s['id'] for s in resp.data.get('results', resp.data)]
        self.assertIn(self.suite.id, ids)

    def test_outsider_does_not_see_suite(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/ui-automation/test-suites/')
        ids = [s['id'] for s in resp.data.get('results', resp.data)]
        self.assertNotIn(self.suite.id, ids)


class TestCaseViewSetAccessTest(DjangoTestCase):
    """P0 数据隔离:TestCase 跟随 project 可见性。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = UiProject.objects.create(
            name='P', base_url='https://example.com', owner=self.owner,
        )
        self.case = UiTestCase.objects.create(
            project=self.project, name='TC', created_by=self.owner,
        )

    def test_owner_sees_case(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/ui-automation/test-cases/')
        self.assertEqual(resp.status_code, 200)
        ids = [c['id'] for c in resp.data.get('results', resp.data)]
        self.assertIn(self.case.id, ids)

    def test_outsider_does_not_see_case(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/ui-automation/test-cases/')
        ids = [c['id'] for c in resp.data.get('results', resp.data)]
        self.assertNotIn(self.case.id, ids)


class AIExecutionRecordViewSetTest(DjangoTestCase):
    """P0 数据隔离 + batch_delete 校验。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = UiProject.objects.create(
            name='P', base_url='https://example.com', owner=self.owner,
        )
        self.record = AIExecutionRecord.objects.create(
            project=self.project, case_name='R', executed_by=self.owner,
        )

    def test_owner_sees_record(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/ui-automation/ai-execution-records/')
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data.get('results', resp.data)]
        self.assertIn(self.record.id, ids)

    def test_outsider_does_not_see_record(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/ui-automation/ai-execution-records/')
        ids = [r['id'] for r in resp.data.get('results', resp.data)]
        self.assertNotIn(self.record.id, ids)

    def test_batch_delete_rejects_empty_ids(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            '/api/ui-automation/ai-execution-records/batch_delete/',
            {'ids': []},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_batch_delete_rejects_non_list_ids(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            '/api/ui-automation/ai-execution-records/batch_delete/',
            {'ids': 'not-a-list'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_batch_delete_only_deletes_accessible(self):
        """outsider 传 owner 的 record id,因 get_queryset 过滤会 404。"""
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.post(
            '/api/ui-automation/ai-execution-records/batch_delete/',
            {'ids': [self.record.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 404)
        # 记录未被删
        self.assertTrue(AIExecutionRecord.objects.filter(id=self.record.id).exists())
