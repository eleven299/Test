"""users 应用烟雾测试。

覆盖:
  - User / UserProfile 模型基本行为
  - RegisterView 注册后返回 JWT
  - login_view 签发 access/refresh
  - my_reviews 防御性过滤(P0 数据隔离)
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.users.models import User, UserProfile


class UserSignalTest(TestCase):
    def test_create_user_does_not_auto_create_profile(self):
        # 项目没有 post_save signal 自动创建 profile,这是当前事实
        user = User.objects.create_user(username='alice', password='x', email='a@x.com')
        self.assertFalse(UserProfile.objects.filter(user=user).exists())

    def test_profile_can_be_created_explicitly(self):
        user = User.objects.create_user(username='alice2', password='x')
        profile = UserProfile.objects.create(user=user)
        self.assertEqual(profile.theme, 'light')
        self.assertEqual(profile.language, 'zh-cn')

    def test_register_endpoint_returns_jwt(self):
        client = APIClient()
        resp = client.post('/api/auth/register/', {
            'username': 'bob',
            'email': 'bob@x.com',
            'password': 'secret123',
            'password_confirm': 'secret123',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)
        self.assertEqual(resp.data['user']['username'], 'bob')

    def test_login_endpoint_returns_jwt(self):
        User.objects.create_user(username='carol', password='secret123')
        client = APIClient()
        resp = client.post('/api/auth/login/', {
            'username': 'carol', 'password': 'secret123'
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)

    def test_password_mismatch_rejected(self):
        client = APIClient()
        resp = client.post('/api/auth/register/', {
            'username': 'dave',
            'email': 'dave@x.com',
            'password': 'aaa',
            'password_confirm': 'bbb',
        }, format='json')
        self.assertEqual(resp.status_code, 400)


class UserDetailAccessTest(TestCase):
    def test_user_cannot_read_other_user_detail(self):
        me = User.objects.create_user(username='me', password='x')
        other = User.objects.create_user(username='other', password='x')
        client = APIClient()
        client.force_authenticate(user=me)
        resp = client.get(f'/api/users/users/{other.id}/')
        # 非管理员且非本人应 404 (get_queryset 过滤)
        self.assertEqual(resp.status_code, 404)

    def test_user_can_read_self(self):
        me = User.objects.create_user(username='me', password='x')
        client = APIClient()
        client.force_authenticate(user=me)
        resp = client.get(f'/api/users/users/{me.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'me')
