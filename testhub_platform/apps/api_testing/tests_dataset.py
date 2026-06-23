"""api_testing TestDataset 与引擎 DDT 联动单元测试。

覆盖:
  - TestDataset 模型基础行为
  - engine._resolve_step_data_set 优先级(dataset vs inline vs override)
  - TestDatasetSerializer 校验
  - TestDatasetViewSet 数据隔离 + CSV 导入
  - POST /datasets/{id}/run/ 端到端
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.api_testing import engine as engine_module
from apps.api_testing.models import (
    ApiProject, ApiRequest, TestSuite, TestSuiteRequest, TestDataset,
    TestStepResult,
)


UserModel = get_user_model()


# ================ TestDataset 模型 ================

class TestDatasetModelTest(TestCase):
    """TestDataset 基础模型行为"""

    @classmethod
    def setUpTestData(cls):
        cls.user = UserModel.objects.create_user(
            username='dataset_owner', password='x', email='d@e.com',
        )
        cls.project = ApiProject.objects.create(
            name='Dataset 测试项目', project_type='HTTP', status='IN_PROGRESS',
            owner=cls.user,
        )

    def test_default_format_inline(self):
        ds = TestDataset.objects.create(
            project=self.project, name='默认格式',
            created_by=self.user,
        )
        self.assertEqual(ds.format, 'inline')
        self.assertEqual(ds.data, [])
        self.assertEqual(ds.columns, [])

    def test_str_includes_format(self):
        ds = TestDataset.objects.create(
            project=self.project, name='登录数据', format='csv',
            data=[{'a': 1}], created_by=self.user,
        )
        self.assertIn('登录数据', str(ds))
        self.assertIn('CSV', str(ds))


# ================ engine._resolve_step_data_set ================

class EngineResolveDataSetTest(TestCase):
    """_resolve_step_data_set 应优先 dataset,退回 inline"""

    @classmethod
    def setUpTestData(cls):
        cls.user = UserModel.objects.create_user(
            username='resolve_tester', password='x', email='r@e.com',
        )
        cls.project = ApiProject.objects.create(
            name='Resolve 项目', project_type='HTTP', status='IN_PROGRESS',
            owner=cls.user,
        )
        cls.suite = TestSuite.objects.create(
            project=cls.project, name='Resolve 套件', created_by=cls.user,
        )
        cls.req = ApiRequest.objects.create(
            name='接口', method='GET', url='https://x/',
            headers=[], params={}, body={}, created_by=cls.user,
        )
        cls.step = TestSuiteRequest.objects.create(
            test_suite=cls.suite, request=cls.req, order=1,
        )

    def test_dataset_takes_priority_over_inline(self):
        ds = TestDataset.objects.create(
            project=self.project, name='外部',
            data=[{'u': 'admin'}, {'u': 'guest'}],
            created_by=self.user,
        )
        self.step.dataset = ds
        self.step.data_set = [{'inline': True}]
        self.step.save()

        resolved = engine_module.TestExecutionEngine._resolve_step_data_set(self.step)
        self.assertEqual(resolved, [{'u': 'admin'}, {'u': 'guest'}])

    def test_empty_dataset_falls_back_to_inline(self):
        ds = TestDataset.objects.create(
            project=self.project, name='空',
            data=[], created_by=self.user,
        )
        self.step.dataset = ds
        self.step.data_set = [{'inline': True}]
        self.step.save()

        resolved = engine_module.TestExecutionEngine._resolve_step_data_set(self.step)
        self.assertEqual(resolved, [{'inline': True}])

    def test_no_dataset_uses_inline(self):
        self.step.dataset = None
        self.step.data_set = [{'x': 1}]
        self.step.save()

        resolved = engine_module.TestExecutionEngine._resolve_step_data_set(self.step)
        self.assertEqual(resolved, [{'x': 1}])

    def test_override_takes_priority_over_dataset(self):
        """dataset_override 优先于 step.dataset"""
        ds_step = TestDataset.objects.create(
            project=self.project, name='步骤绑定',
            data=[{'u': 'admin'}], created_by=self.user,
        )
        ds_override = TestDataset.objects.create(
            project=self.project, name='临时覆盖',
            data=[{'u': 'iter-1'}, {'u': 'iter-2'}],
            created_by=self.user,
        )
        self.step.dataset = ds_step
        self.step.data_set = [{'inline': True}]
        self.step.save()

        resolved = engine_module.TestExecutionEngine._resolve_step_data_set(
            self.step, override_dataset=ds_override
        )
        self.assertEqual(resolved, [{'u': 'iter-1'}, {'u': 'iter-2'}])

    def test_empty_override_falls_back_to_step_dataset(self):
        """dataset_override 为空列表时退回 step.dataset"""
        ds_step = TestDataset.objects.create(
            project=self.project, name='步骤绑定',
            data=[{'u': 'admin'}], created_by=self.user,
        )
        ds_override_empty = TestDataset.objects.create(
            project=self.project, name='空覆盖',
            data=[], created_by=self.user,
        )
        self.step.dataset = ds_step
        self.step.save()

        resolved = engine_module.TestExecutionEngine._resolve_step_data_set(
            self.step, override_dataset=ds_override_empty
        )
        self.assertEqual(resolved, [{'u': 'admin'}])

    def test_override_none_falls_back_to_step_dataset(self):
        """dataset_override=None 时退回 step.dataset / inline"""
        ds_step = TestDataset.objects.create(
            project=self.project, name='步骤绑定',
            data=[{'u': 'admin'}], created_by=self.user,
        )
        self.step.dataset = ds_step
        self.step.save()

        resolved = engine_module.TestExecutionEngine._resolve_step_data_set(
            self.step, override_dataset=None
        )
        self.assertEqual(resolved, [{'u': 'admin'}])


# ================ TestDatasetSerializer ================

class TestDatasetSerializerTest(TestCase):
    """TestDatasetSerializer 校验逻辑"""

    @classmethod
    def setUpTestData(cls):
        cls.user = UserModel.objects.create_user(
            username='ser_tester', password='x', email='s@e.com',
        )
        cls.project = ApiProject.objects.create(
            name='Ser 项目', project_type='HTTP', status='IN_PROGRESS',
            owner=cls.user,
        )

    def _make_serializer(self, data, **kwargs):
        from apps.api_testing.serializers import TestDatasetSerializer
        return TestDatasetSerializer(data=data, context={'request': type('R', (), {'user': self.user})}, **kwargs)

    def test_non_list_data_rejected(self):
        s = self._make_serializer({
            'project': self.project.id, 'name': 'x', 'data': {'a': 1},
        })
        self.assertFalse(s.is_valid())
        self.assertIn('data', s.errors)

    def test_non_dict_row_rejected(self):
        s = self._make_serializer({
            'project': self.project.id, 'name': 'x', 'data': ['string_row'],
        })
        self.assertFalse(s.is_valid())
        self.assertIn('data', s.errors)

    def test_valid_list_of_dicts_accepted(self):
        s = self._make_serializer({
            'project': self.project.id, 'name': 'ok',
            'data': [{'a': 1}, {'a': 2}],
        })
        self.assertTrue(s.errors == {} if s.is_valid() else False, s.errors)


# ================ TestDatasetViewSet ================

class TestDatasetViewSetTest(TestCase):
    """ViewSet 数据隔离与 CSV 导入"""

    @classmethod
    def setUpTestData(cls):
        cls.user = UserModel.objects.create_user(
            username='ds_api_user', password='x', email='a@b.com',
        )
        cls.other_user = UserModel.objects.create_user(
            username='ds_other', password='x', email='o@b.com',
        )
        cls.project = ApiProject.objects.create(
            name='ViewSet 项目', project_type='HTTP', status='IN_PROGRESS',
            owner=cls.user,
        )
        cls.other_project = ApiProject.objects.create(
            name='别人的项目', project_type='HTTP', status='IN_PROGRESS',
            owner=cls.other_user,
        )
        TestDataset.objects.create(
            project=cls.project, name='我的数据集', format='inline',
            data=[{'a': 1}], created_by=cls.user,
        )
        TestDataset.objects.create(
            project=cls.other_project, name='别人的数据集', format='inline',
            data=[{'a': 2}], created_by=cls.other_user,
        )

    def _client(self):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(self.user)
        return c

    def test_queryset_isolation(self):
        c = self._client()
        r = c.get('/api/api-testing/datasets/')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        items = body.get('results', body)
        names = [it['name'] for it in items]
        self.assertIn('我的数据集', names)
        self.assertNotIn('别人的数据集', names)

    def test_csv_import_creates_rows(self):
        ds = TestDataset.objects.create(
            project=self.project, name='CSV 导入目标', created_by=self.user,
        )
        c = self._client()
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_bytes = b'username,password\nadmin,123\nguest,abc\n'
        upload = SimpleUploadedFile('t.csv', csv_bytes, content_type='text/csv')
        r = c.post(
            f'/api/api-testing/datasets/{ds.id}/import-csv/',
            {'file': upload, 'has_header': 'true'},
            format='multipart',
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body['row_count'], 2)
        self.assertEqual(body['columns'], ['username', 'password'])

        ds.refresh_from_db()
        self.assertEqual(ds.format, 'csv')
        self.assertEqual(ds.data[0]['username'], 'admin')

    def test_csv_import_sanitizes_formula_injection(self):
        ds = TestDataset.objects.create(
            project=self.project, name='CSV 注入测试', created_by=self.user,
        )
        c = self._client()
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_bytes = b'name\n=cmd|calc\n+5\n@SUM\n'
        upload = SimpleUploadedFile('t.csv', csv_bytes, content_type='text/csv')
        r = c.post(
            f'/api/api-testing/datasets/{ds.id}/import-csv/',
            {'file': upload},
            format='multipart',
        )
        self.assertEqual(r.status_code, 200, r.content)
        ds.refresh_from_db()
        values = [row['name'] for row in ds.data]
        self.assertIn("'=cmd|calc", values)
        self.assertIn("'+5", values)
        self.assertIn("'@SUM", values)


# ================ 数据集批量执行接口 ================

class DatasetRunAPITest(TestCase):
    """POST /api/api-testing/datasets/{id}/run/ 端到端测试

    通过 mock requests.request 让 engine 不真正发 HTTP 请求,
    覆盖:空数据集 / 无权限套件 / 正常执行 / 套件不存在 / 缺 test_suite_id。
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = UserModel.objects.create_user(
            username='ds_run_user', password='x', email='r1@e.com',
        )
        cls.other_user = UserModel.objects.create_user(
            username='ds_run_other', password='x', email='r2@e.com',
        )
        cls.project = ApiProject.objects.create(
            name='Run API 测试项目', project_type='HTTP', status='IN_PROGRESS',
            owner=cls.user,
        )
        cls.other_project = ApiProject.objects.create(
            name='别人的项目 RunAPI', project_type='HTTP', status='IN_PROGRESS',
            owner=cls.other_user,
        )
        cls.suite = TestSuite.objects.create(
            project=cls.project, name='Run API 套件',
            created_by=cls.user,
        )
        cls.other_suite = TestSuite.objects.create(
            project=cls.other_project, name='别人套件',
            created_by=cls.other_user,
        )
        # 两个接口都带状态码断言,mock 返回 200 让全部步骤通过
        cls.req_a = ApiRequest.objects.create(
            name='A', method='GET', url='https://x/a/{{u}}',
            headers=[], params={}, body={},
            assertions=[{'source': 'status_code', 'operator': 'equals', 'expected': 200}],
            created_by=cls.user,
        )
        cls.req_b = ApiRequest.objects.create(
            name='B', method='POST', url='https://x/b',
            headers=[], params={}, body={},
            assertions=[{'source': 'status_code', 'operator': 'equals', 'expected': 200}],
            created_by=cls.user,
        )
        cls.step_a = TestSuiteRequest.objects.create(
            test_suite=cls.suite, request=cls.req_a, order=1,
        )
        cls.step_b = TestSuiteRequest.objects.create(
            test_suite=cls.suite, request=cls.req_b, order=2,
        )
        cls.dataset = TestDataset.objects.create(
            project=cls.project, name='DDT 数据',
            data=[{'u': 'alice'}, {'u': 'bob'}, {'u': 'carol'}],
            created_by=cls.user,
        )

    def _client(self):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(self.user)
        return c

    def _patch_requests_200(self):
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"ok": true}'
        mock_resp.headers = {'content-type': 'application/json'}
        mock_resp.json.return_value = {'ok': True}
        return mock.patch.object(engine_module.requests_lib, 'request',
                                  return_value=mock_resp)

    def test_run_dataset_drives_iterations(self):
        """3 行数据集 + 2 个步骤 = 总 6 次执行,全部通过"""
        c = self._client()
        with self._patch_requests_200():
            r = c.post(
                f'/api/api-testing/datasets/{self.dataset.id}/run/',
                {'test_suite_id': self.suite.id},
                format='json',
            )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body['status'], 'COMPLETED')
        self.assertEqual(body['total_requests'], 6)
        self.assertEqual(body['passed_requests'], 6)
        self.assertEqual(body['failed_requests'], 0)

        # step_results 应有 6 条,每个步骤 3 个迭代
        execution_id = body['id']
        steps = TestStepResult.objects.filter(execution_id=execution_id)
        self.assertEqual(steps.count(), 6)
        iterations = sorted({s.iteration for s in steps})
        self.assertEqual(iterations, [0, 1, 2])

        # step.url 保存的是原始 URL,变量替换后的 URL 在 request_snapshot
        # 3 行数据集的 u=alice/bob/carol 应被替换到 GET 步骤的实际 URL
        get_steps = [s for s in steps if s.method == 'GET']
        actual_urls = {
            s.request_snapshot.get('url') for s in get_steps
        }
        self.assertEqual(actual_urls, {
            'https://x/a/alice', 'https://x/a/bob', 'https://x/a/carol'
        })

    def test_run_dataset_does_not_mutate_step_dataset_fk(self):
        """关键:批量执行不能修改 TestSuiteRequest.dataset 关联"""
        self.step_a.dataset = None
        self.step_a.save()
        c = self._client()
        with self._patch_requests_200():
            r = c.post(
                f'/api/api-testing/datasets/{self.dataset.id}/run/',
                {'test_suite_id': self.suite.id},
                format='json',
            )
        self.assertEqual(r.status_code, 200, r.content)

        self.step_a.refresh_from_db()
        self.step_b.refresh_from_db()
        self.assertIsNone(self.step_a.dataset)
        self.assertIsNone(self.step_b.dataset)

    def test_run_dataset_empty_data_rejected(self):
        ds_empty = TestDataset.objects.create(
            project=self.project, name='空', data=[],
            created_by=self.user,
        )
        c = self._client()
        r = c.post(
            f'/api/api-testing/datasets/{ds_empty.id}/run/',
            {'test_suite_id': self.suite.id},
            format='json',
        )
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('为空', r.json().get('error', ''))

    def test_run_dataset_missing_suite_id(self):
        c = self._client()
        r = c.post(
            f'/api/api-testing/datasets/{self.dataset.id}/run/',
            {},
            format='json',
        )
        self.assertEqual(r.status_code, 400, r.content)

    def test_run_dataset_suite_not_found(self):
        c = self._client()
        r = c.post(
            f'/api/api-testing/datasets/{self.dataset.id}/run/',
            {'test_suite_id': 99999999},
            format='json',
        )
        self.assertEqual(r.status_code, 404, r.content)

    def test_run_dataset_other_users_suite_forbidden(self):
        """用户无权使用别人项目下的套件"""
        c = self._client()
        r = c.post(
            f'/api/api-testing/datasets/{self.dataset.id}/run/',
            {'test_suite_id': self.other_suite.id},
            format='json',
        )
        self.assertEqual(r.status_code, 403, r.content)

    def test_run_dataset_with_inline_data_set_step_uses_override(self):
        """步骤原本有 inline data_set,override 应优先于它"""
        self.step_a.data_set = [{'u': 'inline-default'}]
        self.step_a.save()
        c = self._client()
        with self._patch_requests_200():
            r = c.post(
                f'/api/api-testing/datasets/{self.dataset.id}/run/',
                {'test_suite_id': self.suite.id},
                format='json',
            )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body['total_requests'], 6)  # 3 行 × 2 步

    def test_run_dataset_other_user_cannot_access_dataset(self):
        """另一个用户看不到本数据集(404)"""
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(self.other_user)
        r = c.post(
            f'/api/api-testing/datasets/{self.dataset.id}/run/',
            {'test_suite_id': self.suite.id},
            format='json',
        )
        self.assertEqual(r.status_code, 404, r.content)
