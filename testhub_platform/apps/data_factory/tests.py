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
