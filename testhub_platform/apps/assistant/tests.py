"""assistant 应用烟雾测试。

重点验证:
  - DifyConfig 全局唯一激活配置(get_active_config)
  - DifyConfig API 列表接口对 api_key 做掩码(不返回明文)
  - AssistantSession 用户隔离(P0):A 看不到 B 的会话
  - ChatMessage / AssistantMessage 归属 session
"""
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.assistant.models import (
    DifyConfig, AssistantSession, ChatMessage, AssistantMessage,
)


class DifyConfigTest(DjangoTestCase):
    def test_create_defaults(self):
        cfg = DifyConfig.objects.create(
            api_url='https://api.dify.ai',
            api_key='sk-secret-xxx',
        )
        self.assertTrue(cfg.is_active)

    def test_get_active_config_returns_first_active(self):
        DifyConfig.objects.create(
            api_url='https://a', api_key='k1', is_active=False,
        )
        active = DifyConfig.objects.create(
            api_url='https://b', api_key='k2', is_active=True,
        )
        result = DifyConfig.get_active_config()
        self.assertEqual(result.id, active.id)

    def test_get_active_config_none_when_all_inactive(self):
        DifyConfig.objects.create(
            api_url='https://a', api_key='k1', is_active=False,
        )
        self.assertIsNone(DifyConfig.get_active_config())


class DifyConfigApiTest(DjangoTestCase):
    """API 层验证:list 接口必须对 api_key 做掩码,不能返回明文。"""

    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')

    def test_list_masks_api_key(self):
        """api_key 字段在 serializer 中是 write_only=True,列表接口不应返回明文。"""
        DifyConfig.objects.create(
            api_url='https://api.dify.ai',
            api_key='sk-super-secret-key-12345',
            is_active=True,
        )
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/assistant/config/dify/')
        self.assertEqual(resp.status_code, 200)
        # 明文 key 绝不能出现在响应中
        self.assertNotIn('sk-super-secret-key-12345', str(resp.data))
        self.assertNotIn('api_key', resp.data)

    def test_list_returns_404_when_no_active_config(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        resp = c.get('/api/assistant/config/dify/')
        self.assertEqual(resp.status_code, 404)


class AssistantSessionIsolationTest(DjangoTestCase):
    """P0 数据隔离:A 用户看不到 B 用户的会话。"""

    def setUp(self):
        self.user_a = User.objects.create_user(username='a', password='x')
        self.user_b = User.objects.create_user(username='b', password='x')
        self.session_a = AssistantSession.objects.create(
            user=self.user_a, session_id='sa-1', title='A 的会话',
        )

    def test_user_a_sees_own_session(self):
        c = APIClient()
        c.force_authenticate(user=self.user_a)
        resp = c.get('/api/assistant/sessions/')
        self.assertEqual(resp.status_code, 200)
        ids = [s['session_id'] for s in resp.data.get('results', resp.data)]
        self.assertIn('sa-1', ids)

    def test_user_b_cannot_see_user_a_session(self):
        c = APIClient()
        c.force_authenticate(user=self.user_b)
        resp = c.get('/api/assistant/sessions/')
        self.assertEqual(resp.status_code, 200)
        ids = [s['session_id'] for s in resp.data.get('results', resp.data)]
        self.assertNotIn('sa-1', ids)


class ChatMessageTest(DjangoTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')
        self.session = AssistantSession.objects.create(
            user=self.user, session_id='s1',
        )

    def test_create_user_message(self):
        msg = ChatMessage.objects.create(
            session=self.session, role='user', content='你好',
        )
        self.assertEqual(msg.role, 'user')
        self.assertEqual(msg.content, '你好')

    def test_message_ordering(self):
        ChatMessage.objects.create(session=self.session, role='user', content='first')
        ChatMessage.objects.create(session=self.session, role='assistant', content='second')
        msgs = list(ChatMessage.objects.all())
        self.assertEqual([m.content for m in msgs], ['first', 'second'])

    def test_cascade_delete(self):
        ChatMessage.objects.create(session=self.session, role='user', content='hi')
        AssistantMessage.objects.create(
            session=self.session, message_type='user', content='legacy',
        )
        self.session.delete()
        self.assertEqual(ChatMessage.objects.count(), 0)
        self.assertEqual(AssistantMessage.objects.count(), 0)
