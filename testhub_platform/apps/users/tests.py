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


class LoginViewExtraTest(TestCase):
    """login_view 异常路径。"""

    def test_wrong_password_rejected(self):
        User.objects.create_user(username='alice', password='secret123')
        c = APIClient()
        resp = c.post('/api/auth/login/',
                       {'username': 'alice', 'password': 'wrong'},
                       format='json')
        self.assertEqual(resp.status_code, 400)

    def test_missing_username_rejected(self):
        c = APIClient()
        resp = c.post('/api/auth/login/', {'password': 'x'}, format='json')
        self.assertEqual(resp.status_code, 400)


class LogoutViewTest(TestCase):
    """logout_view 默认 IsAuthenticated,未登录返回 401;登录后返回 200。"""

    def test_unauthenticated_returns_401(self):
        c = APIClient()
        resp = c.post('/api/auth/logout/')
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_logout_without_refresh_returns_200(self):
        user = User.objects.create_user(username='u', password='x')
        c = APIClient()
        c.force_authenticate(user=user)
        resp = c.post('/api/auth/logout/')
        self.assertEqual(resp.status_code, 200)


class ProfileViewTest(TestCase):
    """/api/auth/profile/ 登录态校验。"""

    def test_unauthenticated_returns_401(self):
        c = APIClient()
        resp = c.get('/api/auth/profile/')
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_returns_self(self):
        user = User.objects.create_user(username='u', password='x')
        c = APIClient()
        c.force_authenticate(user=user)
        resp = c.get('/api/auth/profile/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'u')


class GetCurrentUserTest(TestCase):
    """/api/users/me/ 端点。"""

    def test_unauthenticated_returns_401(self):
        c = APIClient()
        resp = c.get('/api/users/me/')
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_returns_self(self):
        user = User.objects.create_user(username='u', password='x')
        c = APIClient()
        c.force_authenticate(user=user)
        resp = c.get('/api/users/me/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'u')


class UserListViewTest(TestCase):
    """UserListView 认证用户可访问。"""

    def test_unauthenticated_rejected(self):
        c = APIClient()
        resp = c.get('/api/users/users/')
        # DRF 默认 401 (未登录)
        self.assertIn(resp.status_code, (401, 403))

    def test_authenticated_returns_user_list(self):
        User.objects.create_user(username='alice', password='x')
        User.objects.create_user(username='bob', password='x')
        me = User.objects.create_user(username='me', password='x')
        c = APIClient()
        c.force_authenticate(user=me)
        resp = c.get('/api/users/users/')
        self.assertEqual(resp.status_code, 200)
        page = resp.data.get('results', resp.data)
        usernames = {u['username'] for u in page}
        self.assertEqual(usernames, {'alice', 'bob', 'me'})


class UserDetailAdminTest(TestCase):
    """P0 数据隔离:is_staff 用户可读他人信息;普通用户 404。"""

    def test_staff_can_read_other_users(self):
        admin = User.objects.create_user(
            username='admin', password='x', is_staff=True,
        )
        other = User.objects.create_user(username='other', password='x')
        c = APIClient()
        c.force_authenticate(user=admin)
        resp = c.get(f'/api/users/users/{other.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'other')


class SendRegisterCodeValidationTest(TestCase):
    """send_register_code 输入校验:所有路径在调 Redis 之前返回 400。"""

    def test_missing_phone_rejects(self):
        c = APIClient()
        resp = c.post('/api/auth/send-register-code/', {
            'captcha_token': 't', 'captcha_code': 'c',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('手机号', resp.data['error'])

    def test_missing_captcha_rejects(self):
        c = APIClient()
        resp = c.post('/api/auth/send-register-code/', {
            'phone': '13800138000',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('图形验证码', resp.data['error'])

    def test_login_mode_unregistered_phone_rejects(self):
        c = APIClient()
        resp = c.post('/api/auth/send-register-code/', {
            'phone': '13800138000',
            'captcha_token': 't', 'captcha_code': 'c',
            'mode': 'login',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('未注册', resp.data['error'])

    def test_register_mode_already_registered_phone_rejects(self):
        User.objects.create_user(
            username='u', password='x', phone='13800138000',
        )
        c = APIClient()
        resp = c.post('/api/auth/send-register-code/', {
            'phone': '13800138000',
            'captcha_token': 't', 'captcha_code': 'c',
            'mode': 'register',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('已被注册', resp.data['error'])


class SmsLoginValidationTest(TestCase):
    """sms_login_view 输入校验:手机号/验证码格式不正确在调 Redis 前返回 400。"""

    def test_missing_phone_rejects(self):
        c = APIClient()
        resp = c.post('/api/auth/sms-login/', {
            'verify_code': '1234', 'verify_code_token': 't',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('手机号', resp.data['error'])

    def test_invalid_phone_format_rejects(self):
        c = APIClient()
        resp = c.post('/api/auth/sms-login/', {
            'phone': '12345',
            'verify_code': '1234', 'verify_code_token': 't',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('格式不正确', resp.data['error'])

    def test_missing_verify_code_rejects(self):
        c = APIClient()
        resp = c.post('/api/auth/sms-login/', {
            'phone': '13800138000',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('短信验证码', resp.data['error'])
