"""api_testing 应用 view 层烟雾测试。

引擎/工具层单元测试在 tests.py(88 个),model 层在 tests_model.py(7 个)。
本文件覆盖 view 层关键端点,重点验证:
  - ScheduledTaskViewSet:admin/普通用户 list 隔离、run_now 403 权限、activate/pause 状态守卫、execution_logs 403
  - TestExecutionViewSet:按可访问项目隔离
  - AIServiceConfigViewSet:created_by 隔离 + test_connection 校验(mocked requests.post)
  - TestDatasetViewSet.bulk_delete:只删自己数据集 + 空 ids 拒绝
  - RequestHistoryViewSet.batch_delete:按可访问项目过滤
  - TaskExecutionLogViewSet / OperationLogViewSet:数据隔离
  - ApiProjectViewSet.create_sample_project:重复创建保护
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.api_testing.models import (
    ApiProject, ApiCollection, ApiRequest, TestDataset, TestSuite, TestExecution,
    ScheduledTask, AIServiceConfig, RequestHistory, TaskExecutionLog, OperationLog,
)


class ScheduledTaskViewSetTest(DjangoTestCase):
    """ScheduledTaskViewSet 关键守卫:
      - get_queryset: admin 全量 / 普通用户只看自己
      - run_now: 非创建者(非 admin) 403
      - activate/pause: 已在目标状态返回 400
      - execution_logs: 同 run_now 权限
    """

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.other = User.objects.create_user(username='other', password='x')
        self.admin = User.objects.create_user(
            username='admin', password='x', is_staff=True,
        )
        self.task = ScheduledTask.objects.create(
            name='T', task_type='TEST_SUITE', trigger_type='ONCE',
            created_by=self.owner,
        )

    def test_owner_lists_own_task(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/api-testing/scheduled-tasks/')
        self.assertEqual(resp.status_code, 200)
        ids = [t['id'] for t in resp.data.get('results', resp.data)]
        self.assertIn(self.task.id, ids)

    def test_other_does_not_see_owner_task(self):
        c = APIClient()
        c.force_authenticate(user=self.other)
        resp = c.get('/api/api-testing/scheduled-tasks/')
        ids = [t['id'] for t in resp.data.get('results', resp.data)]
        self.assertNotIn(self.task.id, ids)

    def test_admin_sees_all_tasks(self):
        c = APIClient()
        c.force_authenticate(user=self.admin)
        resp = c.get('/api/api-testing/scheduled-tasks/')
        ids = [t['id'] for t in resp.data.get('results', resp.data)]
        self.assertIn(self.task.id, ids)

    def test_run_now_rejects_non_owner(self):
        """P0 权限:other 用户不能执行 owner 的任务。"""
        c = APIClient()
        c.force_authenticate(user=self.other)
        # get_object 也走 get_queryset,普通用户根本拿不到 -> 404
        resp = c.post(f'/api/api-testing/scheduled-tasks/{self.task.id}/run_now/')
        self.assertIn(resp.status_code, (403, 404))

    def test_activate_rejects_already_active(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        # 默认 status='ACTIVE'
        resp = c.post(f'/api/api-testing/scheduled-tasks/{self.task.id}/activate/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('激活', resp.data['error'])

    def test_pause_then_pause_again_rejects(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        # 第一次 pause 成功
        resp1 = c.post(f'/api/api-testing/scheduled-tasks/{self.task.id}/pause/')
        self.assertEqual(resp1.status_code, 200)
        # 已 PAUSED,再 pause 应 400
        resp2 = c.post(f'/api/api-testing/scheduled-tasks/{self.task.id}/pause/')
        self.assertEqual(resp2.status_code, 400)
        self.assertIn('暂停', resp2.data['error'])

    def test_execution_logs_rejects_non_owner(self):
        c = APIClient()
        c.force_authenticate(user=self.other)
        resp = c.get(f'/api/api-testing/scheduled-tasks/{self.task.id}/execution_logs/')
        self.assertIn(resp.status_code, (403, 404))

    def test_execution_logs_visible_to_owner(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get(f'/api/api-testing/scheduled-tasks/{self.task.id}/execution_logs/')
        self.assertEqual(resp.status_code, 200)


class TestExecutionViewSetTest(DjangoTestCase):
    """P0 数据隔离:TestExecution 按 test_suite.project 的可访问项目过滤。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='out', password='x')
        self.project = ApiProject.objects.create(
            name='P', project_type='HTTP', status='NOT_STARTED', owner=self.owner,
        )
        self.suite = TestSuite.objects.create(
            name='S', project=self.project, created_by=self.owner,
        )
        self.execution = TestExecution.objects.create(
            test_suite=self.suite,
            status='COMPLETED', trigger_source='manual',
            executed_by=self.owner,
        )

    def test_owner_lists_execution(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/api-testing/test-executions/')
        self.assertEqual(resp.status_code, 200)
        ids = [e['id'] for e in resp.data.get('results', resp.data)]
        self.assertIn(self.execution.id, ids)

    def test_outsider_does_not_see_execution(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/api-testing/test-executions/')
        self.assertEqual(resp.status_code, 200)
        ids = [e['id'] for e in resp.data.get('results', resp.data)]
        self.assertNotIn(self.execution.id, ids)


class AIServiceConfigViewSetTest(DjangoTestCase):
    """P0 数据隔离:created_by 用户作用域 + test_connection 校验。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.other = User.objects.create_user(username='other', password='x')
        self.cfg = AIServiceConfig.objects.create(
            name='owner-cfg', service_type='deepseek', role='description',
            api_key='sk-owner', base_url='https://api.deepseek.com',
            model_name='deepseek-chat', created_by=self.owner,
        )

    def test_owner_lists_own_config(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/api-testing/ai-service-configs/')
        self.assertEqual(resp.status_code, 200)
        ids = [c['id'] for c in resp.data.get('results', resp.data)]
        self.assertIn(self.cfg.id, ids)

    def test_other_does_not_see_owner_config(self):
        c = APIClient()
        c.force_authenticate(user=self.other)
        resp = c.get('/api/api-testing/ai-service-configs/')
        ids = [c['id'] for c in resp.data.get('results', resp.data)]
        self.assertNotIn(self.cfg.id, ids)

    def test_test_connection_rejects_missing_config_id(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post('/api/api-testing/ai-service-configs/test_connection/', {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('配置ID', resp.data['error'])

    def test_test_connection_rejects_not_found(self):
        """传别人的 config_id 应视为不存在(因 queryset 加了 created_by 过滤)。"""
        c = APIClient()
        c.force_authenticate(user=self.other)
        resp = c.post(
            '/api/api-testing/ai-service-configs/test_connection/',
            {'config_id': self.cfg.id},
            format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_test_connection_success_with_mocked_post(self):
        """mock requests.post 返回 200,view 应回 success。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch(
            'apps.api_testing.views.requests.post', return_value=mock_resp,
        ) as mock_post:
            resp = c.post(
                '/api/api-testing/ai-service-configs/test_connection/',
                {'config_id': self.cfg.id},
                format='json',
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'success')
        # 验证 view 真的发了请求
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn('chat/completions', args[0])
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer sk-owner')

    def test_test_connection_reports_non_200(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = 'invalid api key'
        with patch(
            'apps.api_testing.views.requests.post', return_value=mock_resp,
        ):
            resp = c.post(
                '/api/api-testing/ai-service-configs/test_connection/',
                {'config_id': self.cfg.id},
                format='json',
            )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('401', resp.data['error'])


class TestDatasetBulkDeleteTest(DjangoTestCase):
    """bulk_delete 关键守卫:
      - ids 经 get_queryset 过滤,只能删自己可见的数据集
      - 空 ids / 非列表应拒绝
    """

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.other = User.objects.create_user(username='other', password='x')
        self.owner_project = ApiProject.objects.create(
            name='P1', project_type='HTTP', status='NOT_STARTED', owner=self.owner,
        )
        self.other_project = ApiProject.objects.create(
            name='P2', project_type='HTTP', status='NOT_STARTED', owner=self.other,
        )
        self.owner_ds = TestDataset.objects.create(
            project=self.owner_project, name='owner-ds',
            created_by=self.owner,
        )
        self.other_ds = TestDataset.objects.create(
            project=self.other_project, name='other-ds',
            created_by=self.other,
        )

    def test_owner_can_delete_own_dataset(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            '/api/api-testing/datasets/bulk-delete/',
            {'ids': [self.owner_ds.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(TestDataset.objects.filter(id=self.owner_ds.id).exists())

    def test_owner_cannot_delete_others_dataset(self):
        """传别人的 id 应被 queryset 过滤掉,deleted=0。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            '/api/api-testing/datasets/bulk-delete/',
            {'ids': [self.other_ds.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        # other 的数据集仍然存在
        self.assertTrue(TestDataset.objects.filter(id=self.other_ds.id).exists())
        self.assertEqual(resp.data['deleted'], 0)

    def test_bulk_delete_rejects_empty_ids(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post('/api/api-testing/datasets/bulk-delete/', {'ids': []}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_bulk_delete_rejects_missing_ids(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post('/api/api-testing/datasets/bulk-delete/', {}, format='json')
        self.assertEqual(resp.status_code, 400)


class RequestHistoryBatchDeleteTest(DjangoTestCase):
    """batch_delete 关键守卫:只能删除自己可见项目下的历史记录。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.other = User.objects.create_user(username='other', password='x')
        # owner 项目 + 历史
        self.owner_project = ApiProject.objects.create(
            name='P1', project_type='HTTP', status='NOT_STARTED', owner=self.owner,
        )
        owner_collection = ApiCollection.objects.create(name='C1', project=self.owner_project)
        owner_req = ApiRequest.objects.create(
            collection=owner_collection, name='R1', method='GET', url='/x',
            created_by=self.owner,
        )
        self.owner_history = RequestHistory.objects.create(
            request=owner_req, request_data={}, executed_by=self.owner,
        )
        # other 项目 + 历史
        self.other_project = ApiProject.objects.create(
            name='P2', project_type='HTTP', status='NOT_STARTED', owner=self.other,
        )
        other_collection = ApiCollection.objects.create(name='C2', project=self.other_project)
        other_req = ApiRequest.objects.create(
            collection=other_collection, name='R2', method='GET', url='/y',
            created_by=self.other,
        )
        self.other_history = RequestHistory.objects.create(
            request=other_req, request_data={}, executed_by=self.other,
        )

    def test_owner_can_delete_own_history(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            '/api/api-testing/histories/batch-delete/',
            {'ids': [self.owner_history.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(RequestHistory.objects.filter(id=self.owner_history.id).exists())

    def test_owner_cannot_delete_other_history(self):
        """传 other 的 history id 应被 queryset 过滤掉。"""
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            '/api/api-testing/histories/batch-delete/',
            {'ids': [self.other_history.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(RequestHistory.objects.filter(id=self.other_history.id).exists())

    def test_batch_delete_rejects_empty_ids(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post('/api/api-testing/histories/batch-delete/', {'ids': []}, format='json')
        self.assertEqual(resp.status_code, 400)


class TaskExecutionLogAccessTest(DjangoTestCase):
    """P0 数据隔离:只能看到自己创建的 task 的执行日志。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.other = User.objects.create_user(username='other', password='x')
        owner_task = ScheduledTask.objects.create(
            name='T1', task_type='TEST_SUITE', trigger_type='ONCE',
            created_by=self.owner,
        )
        other_task = ScheduledTask.objects.create(
            name='T2', task_type='TEST_SUITE', trigger_type='ONCE',
            created_by=self.other,
        )
        self.owner_log = TaskExecutionLog.objects.create(
            task=owner_task, status='PENDING', executed_by=self.owner,
        )
        self.other_log = TaskExecutionLog.objects.create(
            task=other_task, status='PENDING', executed_by=self.other,
        )

    def test_owner_sees_own_log(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/api-testing/task-execution-logs/')
        self.assertEqual(resp.status_code, 200)
        ids = [l['id'] for l in resp.data.get('results', resp.data)]
        self.assertIn(self.owner_log.id, ids)
        self.assertNotIn(self.other_log.id, ids)


class OperationLogAccessTest(DjangoTestCase):
    """P0 数据隔离:普通用户只能看自己的操作日志,admin 可看全部。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.other = User.objects.create_user(username='other', password='x')
        self.admin = User.objects.create_user(
            username='admin', password='x', is_staff=True,
        )
        self.owner_log = OperationLog.objects.create(
            operation_type='create', resource_type='project',
            resource_id=1, resource_name='P', user=self.owner,
        )
        self.other_log = OperationLog.objects.create(
            operation_type='create', resource_type='project',
            resource_id=2, resource_name='Q', user=self.other,
        )

    def test_owner_sees_own_log_only(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/api-testing/operation-logs/')
        self.assertEqual(resp.status_code, 200)
        ids = [l['id'] for l in resp.data.get('results', resp.data)]
        self.assertIn(self.owner_log.id, ids)
        self.assertNotIn(self.other_log.id, ids)

    def test_admin_sees_all_logs(self):
        c = APIClient()
        c.force_authenticate(user=self.admin)
        resp = c.get('/api/api-testing/operation-logs/')
        ids = [l['id'] for l in resp.data.get('results', resp.data)]
        self.assertIn(self.owner_log.id, ids)
        self.assertIn(self.other_log.id, ids)


class CreateSampleProjectTest(DjangoTestCase):
    """create_sample_project 关键守卫:每个用户只能有一份示例项目。"""

    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')

    def test_first_call_creates_sample(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.post('/api/api-testing/projects/create-sample/')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            ApiProject.objects.filter(owner=self.user, name='宠物店API示例项目').exists()
        )

    def test_second_call_rejected(self):
        """重复创建应返回 400。"""
        c = APIClient()
        c.force_authenticate(user=self.user)
        c.post('/api/api-testing/projects/create-sample/')
        resp = c.post('/api/api-testing/projects/create-sample/')
        self.assertEqual(resp.status_code, 400)
