"""app_automation 应用 view 层烟雾测试。

model 层在 test_models.py。本文件覆盖 view 层关键端点,重点验证:
  - AppProjectViewSet:owner/member 可见,outsider 不可见(P0 数据隔离)
  - AppElementViewSet:通过可访问项目过滤(P0) + 上传/分类名校验
  - AppTestCaseViewSet:数据隔离 + execute 必须传 device_id
  - AppTestSuiteViewSet:数据隔离(P0) + 增删用例/执行入参校验
  - AppScheduledTaskViewSet:数据隔离 + pause/resume 状态变更(P0 + P1)
  - AppPackageViewSet:按 created_by 隔离(P0)
  - AppDeviceViewSet:lock/unlock/disconnect/screenshot 入参校验
  - AppComponentViewSet:enabled 过滤
  - AppTestExecutionViewSet:数据隔离 + stop 状态机校验
  - AppNotificationLogViewSet:数据隔离 + retry 状态校验
  - AppDashboardViewSet:statistics 端点
"""
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.app_automation.models import (
    AppProject, AppElement, AppTestCase,
    AppTestSuite, AppTestSuiteCase, AppScheduledTask, AppPackage,
    AppDevice, AppComponent, AppTestExecution, AppNotificationLog,
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


class AppDeviceViewSetTest(DjangoTestCase):
    """设备 lock/unlock/disconnect/screenshot 入参校验。

    discover/connect/screenshot 涉及 ADB 子进程,只测输入校验路径。
    """

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.other = User.objects.create_user(username='other', password='x')
        self.device = AppDevice.objects.create(
            device_id='emulator-5554', name='模拟器',
            status='available', connection_type='emulator',
        )

    def test_lock_already_locked_rejects(self):
        self.device.lock(self.owner)
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(f'/api/app-automation/devices/{self.device.id}/lock/')
        self.assertEqual(resp.status_code, 400)

    def test_unlock_other_users_device_forbidden(self):
        """P0 数据隔离:他人锁定的设备不可释放。"""
        self.device.lock(self.other)
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(f'/api/app-automation/devices/{self.device.id}/unlock/')
        self.assertEqual(resp.status_code, 403)
        self.device.refresh_from_db()
        self.assertEqual(self.device.locked_by_id, self.other.id)

    def test_disconnect_non_remote_rejects(self):
        """本地模拟器不允许 disconnect(只有 remote/remote_emulator 可以)。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(f'/api/app-automation/devices/{self.device.id}/disconnect/')
        self.assertEqual(resp.status_code, 400)

    def test_connect_missing_ip_rejects(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post('/api/app-automation/devices/connect/', {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_screenshot_offline_rejects(self):
        self.device.status = 'offline'
        self.device.save()
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(f'/api/app-automation/devices/{self.device.id}/screenshot/')
        self.assertEqual(resp.status_code, 400)


class AppComponentViewSetFilterTest(DjangoTestCase):
    """组件库为全局共享资源,无用户隔离;重点验证 enabled 过滤。"""

    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')
        self.on_comp = AppComponent.objects.create(
            name='点击', type='tap', enabled=True,
        )
        self.off_comp = AppComponent.objects.create(
            name='滑动', type='swipe', enabled=False,
        )

    def test_list_returns_all(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/app-automation/components/')
        self.assertEqual(resp.status_code, 200)
        data = resp.data.get('data') or resp.data.get('results') or resp.data
        types = {c.get('type') for c in data}
        self.assertEqual(types, {'tap', 'swipe'})

    def test_filter_enabled_true(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/app-automation/components/?enabled=true')
        data = resp.data.get('data') or resp.data.get('results') or resp.data
        types = {c.get('type') for c in data}
        self.assertEqual(types, {'tap'})


class AppTestSuiteActionsTest(DjangoTestCase):
    """套件增删用例、执行、查询历史的入参校验与状态机。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)
        self.case = AppTestCase.objects.create(
            project=self.project, name='TC', created_by=self.owner,
        )
        self.suite = AppTestSuite.objects.create(
            project=self.project, name='S', created_by=self.owner,
        )

    def test_test_cases_action_returns_ordered(self):
        AppTestSuiteCase.objects.create(
            test_suite=self.suite, test_case=self.case, order=1,
        )
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get(f'/api/app-automation/test-suites/{self.suite.id}/test_cases/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']), 1)
        self.assertEqual(resp.data['data'][0]['test_case']['id'], self.case.id)

    def test_add_test_case_missing_id_rejects(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            f'/api/app-automation/test-suites/{self.suite.id}/add_test_case/',
            {}, format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_add_test_cases_empty_list_rejects(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            f'/api/app-automation/test-suites/{self.suite.id}/add_test_cases/',
            {'test_case_ids': []}, format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_remove_test_case_not_in_suite_404(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            f'/api/app-automation/test-suites/{self.suite.id}/remove_test_case/',
            {'test_case_id': self.case.id}, format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_run_missing_device_id_rejects(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            f'/api/app-automation/test-suites/{self.suite.id}/run/',
            {}, format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_run_empty_suite_rejects(self):
        """P1:执行套件前必须先有用例。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            f'/api/app-automation/test-suites/{self.suite.id}/run/',
            {'device_id': 'emulator-5554'}, format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('用例', resp.data['message'])

    def test_executions_action_returns_history(self):
        """executions action 应返回该套件的执行历史(空也合法)。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get(f'/api/app-automation/test-suites/{self.suite.id}/executions/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('data', resp.data)


class AppTestExecutionViewSetTest(DjangoTestCase):
    """执行记录数据隔离 + stop 状态机。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)
        self.case = AppTestCase.objects.create(
            project=self.project, name='TC', created_by=self.owner,
        )
        self.execution = AppTestExecution.objects.create(
            test_case=self.case, user=self.owner, status='pending',
        )

    def test_owner_sees_execution(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/app-automation/executions/')
        self.assertEqual(resp.status_code, 200)
        ids = [e['id'] for e in resp.data.get('results', resp.data)]
        self.assertIn(self.execution.id, ids)

    def test_outsider_does_not_see_execution(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/app-automation/executions/')
        ids = [e['id'] for e in resp.data.get('results', resp.data)]
        self.assertNotIn(self.execution.id, ids)

    def test_stop_non_stoppable_status_rejects(self):
        """P1 状态机:已完成/已停止的执行不可再次 stop。"""
        self.execution.status = 'completed'
        self.execution.save()
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(f'/api/app-automation/executions/{self.execution.id}/stop/')
        self.assertEqual(resp.status_code, 400)

    def test_stop_pending_executes(self):
        """pending 状态允许 stop,task_id 为空时跳过 Celery revoke。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(f'/api/app-automation/executions/{self.execution.id}/stop/')
        self.assertEqual(resp.status_code, 200)
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, 'stopped')

    def test_ws_status_returns_200(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/app-automation/executions/ws_status/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('websocket', resp.data)


class AppNotificationLogViewSetTest(DjangoTestCase):
    """通知日志数据隔离 + retry 状态校验。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)
        self.task = AppScheduledTask.objects.create(
            name='T', task_type='TEST_CASE', trigger_type='ONCE',
            project=self.project, created_by=self.owner,
        )
        self.log = AppNotificationLog.objects.create(
            task=self.task, notification_type='task_execution',
            status='pending', sent_at=None,
        )

    def test_owner_sees_log(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/app-automation/notification-logs/')
        self.assertEqual(resp.status_code, 200)
        ids = [l['id'] for l in resp.data.get('results', resp.data)]
        self.assertIn(self.log.id, ids)

    def test_outsider_does_not_see_log(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/app-automation/notification-logs/')
        ids = [l['id'] for l in resp.data.get('results', resp.data)]
        self.assertNotIn(self.log.id, ids)

    def test_retry_non_failed_rejects(self):
        """P1 状态机:pending/success/cancelled 状态的通知不允许 retry。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(f'/api/app-automation/notification-logs/{self.log.id}/retry/')
        self.assertEqual(resp.status_code, 400)


class AppDashboardViewSetTest(DjangoTestCase):
    """Dashboard statistics 端点基础可用性。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)

    def test_statistics_returns_200(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/app-automation/dashboard/statistics/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('devices', resp.data['data'])
        self.assertIn('total', resp.data['data']['devices'])


class AppElementUploadValidationTest(DjangoTestCase):
    """元素图片上传、分类名创建的入参校验。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)

    def test_upload_image_no_file_rejects(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post('/api/app-automation/elements/upload/', {}, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_create_image_category_empty_name_rejects(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            '/api/app-automation/elements/image-categories/create/',
            {'name': ''}, format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_image_category_invalid_name_rejects(self):
        """P1:分类名含特殊字符(空格、斜杠等)必须拒绝,防目录穿越。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            '/api/app-automation/elements/image-categories/create/',
            {'name': '../etc'}, format='json',
        )
        self.assertEqual(resp.status_code, 400)
