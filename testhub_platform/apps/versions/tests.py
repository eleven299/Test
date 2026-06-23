"""versions 应用烟雾测试。"""
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.projects.models import Project
from apps.versions.models import Version


class VersionModelTest(DjangoTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)

    def test_create_defaults(self):
        v = Version.objects.create(name='v1.0', created_by=self.owner)
        self.assertFalse(v.is_baseline)
        self.assertEqual(v.description, '')

    def test_many_to_many_projects(self):
        v = Version.objects.create(name='v1.0', created_by=self.owner)
        v.projects.add(self.project)
        self.assertIn(self.project, v.projects.all())
        # 反向
        self.assertIn(v, self.project.versions.all())

    def test_baseline_flag(self):
        v = Version.objects.create(name='v1.0', is_baseline=True, created_by=self.owner)
        self.assertTrue(v.is_baseline)

    def test_ordering(self):
        v1 = Version.objects.create(name='v1', created_by=self.owner)
        v2 = Version.objects.create(name='v2', created_by=self.owner)
        names = [v.name for v in Version.objects.all()]
        # ordering = ['-created_at'], v2 后创建
        self.assertEqual(names, ['v2', 'v1'])


class VersionAccessTest(DjangoTestCase):
    """P0 数据隔离:只能看到自己有权限访问的项目下的版本。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)
        self.version = Version.objects.create(name='v1.0', created_by=self.owner)
        self.version.projects.add(self.project)

    def test_owner_sees_version(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/versions/')
        self.assertEqual(resp.status_code, 200)
        names = [v['name'] for v in resp.data.get('results', resp.data)]
        self.assertIn('v1.0', names)

    def test_outsider_does_not_see_version(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/versions/')
        self.assertEqual(resp.status_code, 200)
        names = [v['name'] for v in resp.data.get('results', resp.data)]
        self.assertNotIn('v1.0', names)


class VersionCreatePermissionTest(DjangoTestCase):
    """P0 权限校验:创建版本时,用户必须对所有指定项目都有访问权限。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)

    def test_owner_can_create_with_accessible_project(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.post(
            '/api/versions/',
            {'name': 'v2.0', 'project_ids': [self.project.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Version.objects.filter(name='v2.0').exists())

    def test_outsider_cannot_create_with_inaccessible_project(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.post(
            '/api/versions/',
            {'name': 'v3.0', 'project_ids': [self.project.id]},
            format='json',
        )
        # ValidationError -> 400
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Version.objects.filter(name='v3.0').exists())

