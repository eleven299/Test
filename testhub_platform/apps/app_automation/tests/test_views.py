"""app_automation 应用 view 层烟雾测试。

model 层在 test_models.py。本文件覆盖 view 层关键端点,重点验证:
  - AppProjectViewSet:owner/member 可见,outsider 不可见(P0 数据隔离)
  - AppElementViewSet:通过可访问项目过滤(P0)
  - AppTestCaseViewSet:数据隔离 + execute 必须传 device_id
  - AppTestSuiteViewSet:数据隔离(P0)
  - AppScheduledTaskViewSet:数据隔离 + pause/resume 状态变更(P0 + P1)
  - AppPackageViewSet:按 created_by 隔离(P0)
"""
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.app_automation.models import (
    AppProject, AppElement, AppTestCase,
    AppTestSuite, AppScheduledTask, AppPackage,
)


class AppProjectViewSetAccessTest(DjangoTestCase):
    """P0 数据隔离:owner / member 可见,outsider 不可见。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.member = User.objects.create_user(username='member', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)
        self.project.members.add(self.member)

    def test_owner_sees_project(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/app-automation/projects/')
        self.assertEqual(resp.status_code, 200)
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertIn(self.project.id, ids)

    def test_member_sees_project(self):
        c = APIClient()
        c.force_authenticate(user=self.member)
        resp = c.get('/api/app-automation/projects/')
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertIn(self.project.id, ids)

    def test_outsider_does_not_see_project(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/app-automation/projects/')
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertNotIn(self.project.id, ids)


class AppElementViewSetAccessTest(DjangoTestCase):
    """P0 数据隔离:AppElement 跟随 project 可见性,outsider 不可见。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)
        self.element = AppElement.objects.create(
            project=self.project,
            name='login-btn',
            element_type='image',
            created_by=self.owner,
        )

    def test_owner_sees_element(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/app-automation/elements/')
        self.assertEqual(resp.status_code, 200)
        ids = [e['id'] for e in resp.data.get('results', resp.data)]
        self.assertIn(self.element.id, ids)

    def test_outsider_does_not_see_element(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/app-automation/elements/')
        ids = [e['id'] for e in resp.data.get('results', resp.data)]
        self.assertNotIn(self.element.id, ids)


class AppTestCaseViewSetAccessTest(DjangoTestCase):
    """P0 数据隔离 + execute 入参校验。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)
        self.case = AppTestCase.objects.create(
            project=self.project, name='TC', created_by=self.owner,
        )

    def test_owner_sees_case(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/app-automation/test-cases/')
        self.assertEqual(resp.status_code, 200)
        ids = [c['id'] for c in resp.data.get('results', resp.data)]
        self.assertIn(self.case.id, ids)

    def test_outsider_does_not_see_case(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/app-automation/test-cases/')
        ids = [c['id'] for c in resp.data.get('results', resp.data)]
        self.assertNotIn(self.case.id, ids)

    def test_execute_rejects_missing_device_id(self):
        """execute action 必须传 device_id。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(f'/api/app-automation/test-cases/{self.case.id}/execute/', {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_outsider_cannot_execute_owner_case(self):
        """outsider 通过 URL 直接访问 case,因 get_queryset 过滤会 404。"""
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.post(
            f'/api/app-automation/test-cases/{self.case.id}/execute/',
            {'device_id': 'xxx'}, format='json',
        )
        self.assertEqual(resp.status_code, 404)


class AppTestSuiteViewSetAccessTest(DjangoTestCase):
    """P0 数据隔离:TestSuite 跟随 project 可见性。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)
        self.suite = AppTestSuite.objects.create(
            project=self.project, name='S', created_by=self.owner,
        )

    def test_owner_sees_suite(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/app-automation/test-suites/')
        self.assertEqual(resp.status_code, 200)
        ids = [s['id'] for s in resp.data.get('results', resp.data)]
        self.assertIn(self.suite.id, ids)

    def test_outsider_does_not_see_suite(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/app-automation/test-suites/')
        ids = [s['id'] for s in resp.data.get('results', resp.data)]
        self.assertNotIn(self.suite.id, ids)


class AppScheduledTaskViewSetTest(DjangoTestCase):
    """P0 数据隔离 + 状态变更:
      - outsider 看不到 owner 项目下的定时任务
      - pause/resume 切换状态
    """

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)
        self.task = AppScheduledTask.objects.create(
            name='T', task_type='TEST_CASE', trigger_type='ONCE',
            project=self.project, created_by=self.owner, status='ACTIVE',
        )

    def test_owner_lists_task(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/app-automation/scheduled-tasks/')
        self.assertEqual(resp.status_code, 200)
        ids = [t['id'] for t in resp.data.get('results', resp.data)]
        self.assertIn(self.task.id, ids)

    def test_outsider_does_not_see_task(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/app-automation/scheduled-tasks/')
        ids = [t['id'] for t in resp.data.get('results', resp.data)]
        self.assertNotIn(self.task.id, ids)

    def test_pause_changes_status(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(f'/api/app-automation/scheduled-tasks/{self.task.id}/pause/')
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'PAUSED')

    def test_resume_changes_status_back(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        c.post(f'/api/app-automation/scheduled-tasks/{self.task.id}/pause/')
        resp = c.post(f'/api/app-automation/scheduled-tasks/{self.task.id}/resume/')
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'ACTIVE')

    def test_outsider_cannot_pause_task(self):
        """outsider 通过 URL 直接访问 task,因 get_queryset 过滤会 404。"""
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.post(f'/api/app-automation/scheduled-tasks/{self.task.id}/pause/')
        self.assertEqual(resp.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'ACTIVE')


class AppPackageViewSetTest(DjangoTestCase):
    """P0 数据隔离:AppPackage 按 created_by 过滤。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.pkg = AppPackage.objects.create(
            name='设置', package_name='com.android.settings', created_by=self.owner,
        )

    def test_owner_sees_package(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/app-automation/packages/')
        self.assertEqual(resp.status_code, 200)
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertIn(self.pkg.id, ids)

    def test_outsider_does_not_see_package(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/app-automation/packages/')
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertNotIn(self.pkg.id, ids)
