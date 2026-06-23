"""core 应用烟雾测试。"""
from django.test import TestCase as DjangoTestCase

from apps.users.models import User
from apps.core.models import UnifiedNotificationConfig


class UnifiedNotificationConfigTest(DjangoTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')

    def test_create_defaults(self):
        cfg = UnifiedNotificationConfig.objects.create(name='默认', created_by=self.owner)
        self.assertEqual(cfg.config_type, 'webhook_feishu')
        self.assertFalse(cfg.is_default)
        self.assertTrue(cfg.is_active)

    def test_get_webhook_bots_unpacks_config(self):
        cfg = UnifiedNotificationConfig.objects.create(
            name='多机器人',
            config_type='webhook_feishu',
            webhook_bots={
                'feishu': {
                    'name': '飞书一号',
                    'webhook_url': 'https://example.com/hook',
                    'enabled': True,
                },
            },
            created_by=self.owner,
        )
        bots = cfg.get_webhook_bots()
        self.assertEqual(len(bots), 1)
        self.assertEqual(bots[0]['type'], 'feishu')
        self.assertEqual(bots[0]['webhook_url'], 'https://example.com/hook')
        self.assertTrue(bots[0]['enable_ui_automation'])

    def test_dingtalk_bot_includes_secret(self):
        cfg = UnifiedNotificationConfig.objects.create(
            name='钉钉',
            webhook_bots={
                'dingtalk': {
                    'webhook_url': 'https://oapi.dingtalk.com/hook',
                    'secret': 'SECxxx',
                },
            },
            created_by=self.owner,
        )
        bots = cfg.get_webhook_bots()
        self.assertEqual(bots[0]['secret'], 'SECxxx')
