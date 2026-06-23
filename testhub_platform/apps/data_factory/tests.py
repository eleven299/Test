"""data_factory 应用烟雾测试。

重点验证:
  - DataFactoryRecord 默认值与基本 CRUD
  - 用户隔离(P0):A 看不到 B 的工具使用记录
"""
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.data_factory.models import DataFactoryRecord


class DataFactoryRecordModelTest(DjangoTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')

    def test_create_defaults(self):
        record = DataFactoryRecord.objects.create(
            user=self.user,
            tool_name='随机手机号',
            tool_category='random',
            tool_scenario='test_data',
            output_data={'value': '13800001111'},
        )
        self.assertTrue(record.is_saved)
        self.assertIsNotNone(record.created_at)

    def test_user_relation(self):
        record = DataFactoryRecord.objects.create(
            user=self.user,
            tool_name='JSON格式化',
            tool_category='json',
            tool_scenario='json',
            output_data={},
        )
        self.assertEqual(record.user, self.user)
        self.assertIn(record, self.user.datafactoryrecord_set.all())


class DataFactoryAccessTest(DjangoTestCase):
    """P0 数据隔离:A 用户列表里看不到 B 的记录。"""

    def setUp(self):
        self.user_a = User.objects.create_user(username='a', password='x')
        self.user_b = User.objects.create_user(username='b', password='x')
        self.record_a = DataFactoryRecord.objects.create(
            user=self.user_a,
            tool_name='A-tool',
            tool_category='random',
            tool_scenario='test_data',
            output_data={'v': 'a'},
        )

    def test_user_a_sees_own_records(self):
        c = APIClient()
        c.force_authenticate(user=self.user_a)
        resp = c.get('/api/data-factory/')
        self.assertEqual(resp.status_code, 200)
        names = [r['tool_name'] for r in resp.data.get('results', resp.data)]
        self.assertIn('A-tool', names)

    def test_user_b_cannot_see_user_a_records(self):
        c = APIClient()
        c.force_authenticate(user=self.user_b)
        resp = c.get('/api/data-factory/')
        self.assertEqual(resp.status_code, 200)
        names = [r['tool_name'] for r in resp.data.get('results', resp.data)]
        self.assertNotIn('A-tool', names)


class DataFactoryExecuteTest(DjangoTestCase):
    """create (执行工具) 端点:成功路径 + 校验失败。"""

    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')

    def test_execute_random_uuid_success(self):
        """random_uuid 无需 input_data,执行成功并落记录。"""
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.post('/api/data-factory/', {
            'tool_name': 'random_uuid',
            'tool_category': 'random',
            'tool_scenario': 'random',
            'input_data': {'version': 4, 'count': 1},
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('record_id', resp.data)
        self.assertEqual(DataFactoryRecord.objects.count(), 1)

    def test_execute_unsupported_category_returns_400(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.post('/api/data-factory/', {
            'tool_name': 'whatever',
            'tool_category': 'no_such_category',
            'tool_scenario': 'unknown',
            'input_data': {},
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.data)

    def test_execute_missing_required_field_returns_400(self):
        """缺少 tool_name 等必填字段,serializer 校验返回 400。"""
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.post('/api/data-factory/', {
            'tool_category': 'random',
            'tool_scenario': 'random',
            'input_data': {},
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('tool_name', resp.data)

    def test_execute_unsaved_skips_record(self):
        """is_saved=False 时不落 DataFactoryRecord。"""
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.post('/api/data-factory/', {
            'tool_name': 'random_uuid',
            'tool_category': 'random',
            'tool_scenario': 'random',
            'input_data': {'version': 4, 'count': 1},
            'is_saved': False,
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('record_id', resp.data)
        self.assertEqual(DataFactoryRecord.objects.count(), 0)


class DataFactoryDestroyTest(DjangoTestCase):
    """destroy 端点数据隔离 + 缓存清理。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.record = DataFactoryRecord.objects.create(
            user=self.owner,
            tool_name='T',
            tool_category='random',
            tool_scenario='random',
            output_data={'v': 1},
        )

    def test_owner_deletes_own_record(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.delete(f'/api/data-factory/{self.record.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(DataFactoryRecord.objects.filter(id=self.record.id).exists())

    def test_outsider_cannot_delete(self):
        """P0:get_queryset 过滤掉他人记录,导致 404。"""
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.delete(f'/api/data-factory/{self.record.id}/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(DataFactoryRecord.objects.filter(id=self.record.id).exists())


class DataFactoryActionsTest(DjangoTestCase):
    """categories / tags / statistics / variable_functions / download_static_file / batch_generate。"""

    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')

    def test_categories_returns_200(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/data-factory/categories/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('categories', resp.data)
        self.assertIn('total_tools', resp.data)
        self.assertGreater(resp.data['total_tools'], 0)

    def test_tags_empty_when_no_records(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/data-factory/tags/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['tags'], [])
        self.assertEqual(resp.data['count'], 0)

    def test_tags_aggregates_from_records(self):
        DataFactoryRecord.objects.create(
            user=self.user, tool_name='T1',
            tool_category='random', tool_scenario='random',
            output_data={}, tags=['prod', 'urgent'],
        )
        DataFactoryRecord.objects.create(
            user=self.user, tool_name='T2',
            tool_category='random', tool_scenario='random',
            output_data={}, tags=['prod'],
        )
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/data-factory/tags/')
        self.assertEqual(set(resp.data['tags']), {'prod', 'urgent'})

    def test_statistics_returns_200(self):
        DataFactoryRecord.objects.create(
            user=self.user, tool_name='T',
            tool_category='random', tool_scenario='random',
            output_data={},
        )
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/data-factory/statistics/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total_records'], 1)
        self.assertIn('category_stats', resp.data)
        self.assertIn('scenario_stats', resp.data)
        self.assertEqual(len(resp.data['recent_tools']), 1)

    def test_variable_functions_returns_200(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/data-factory/variable_functions/')
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.data, list)
        self.assertGreater(len(resp.data), 0)
        # 每个条目都必须包含这些字段
        for item in resp.data:
            self.assertIn('name', item)
            self.assertIn('syntax', item)
            self.assertIn('category', item)

    def test_download_static_file_missing_filename_400(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/data-factory/download_static_file/')
        self.assertEqual(resp.status_code, 400)

    def test_batch_generate_missing_tool_name_400(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.post('/api/data-factory/batch_generate/', {
            'tool_category': 'random',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_batch_generate_missing_tool_category_400(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.post('/api/data-factory/batch_generate/', {
            'tool_name': 'random_uuid',
        }, format='json')
        self.assertEqual(resp.status_code, 400)


class DataFactoryListFilterTest(DjangoTestCase):
    """list 端点的自定义过滤逻辑(tool_category, tool_name__icontains, tags__contains)。"""

    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')
        self.r1 = DataFactoryRecord.objects.create(
            user=self.user, tool_name='random_uuid',
            tool_category='random', tool_scenario='random',
            output_data={}, tags=['prod'],
        )
        self.r2 = DataFactoryRecord.objects.create(
            user=self.user, tool_name='md5_hash',
            tool_category='encryption', tool_scenario='encryption',
            output_data={}, tags=['test'],
        )

    def test_filter_by_tool_category(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/data-factory/?tool_category=random')
        self.assertEqual(resp.status_code, 200)
        names = [r['tool_name'] for r in resp.data['results']]
        self.assertEqual(names, ['random_uuid'])

    def test_filter_by_tool_name_icontains(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/data-factory/?tool_name__icontains=md5')
        names = [r['tool_name'] for r in resp.data['results']]
        self.assertEqual(names, ['md5_hash'])

    def test_filter_by_tags_contains(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/data-factory/?tags__contains=test')
        names = [r['tool_name'] for r in resp.data['results']]
        self.assertEqual(names, ['md5_hash'])
