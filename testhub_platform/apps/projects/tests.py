"""projects 应用烟雾测试。

覆盖:
  - Project / ProjectMember CRUD
  - 成员唯一约束(unique_together)
  - 项目可见性:owner 和 member 可访问,其他人不可
"""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.projects.models import Project, ProjectMember


class ProjectModelTest(TestCase):
    def test_create_project_defaults(self):
        owner = User.objects.create_user(username='owner', password='x')
        p = Project.objects.create(name='P1', owner=owner)
        self.assertEqual(p.status, 'active')

    def test_unique_member(self):
        owner = User.objects.create_user(username='owner', password='x')
        other = User.objects.create_user(username='other', password='x')
        p = Project.objects.create(name='P', owner=owner)
        ProjectMember.objects.create(project=p, user=other, role='tester')
        with self.assertRaises(Exception):
            ProjectMember.objects.create(project=p, user=other, role='tester')


class ProjectAccessTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.member = User.objects.create_user(username='member', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)
        ProjectMember.objects.create(project=self.project, user=self.member)

    def _client_for(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_owner_can_see(self):
        resp = self._client_for(self.owner).get('/api/projects/')
        self.assertEqual(resp.status_code, 200)
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertIn(self.project.id, ids)

    def test_member_can_see(self):
        resp = self._client_for(self.member).get('/api/projects/')
        self.assertEqual(resp.status_code, 200)
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertIn(self.project.id, ids)

    def test_outsider_cannot_see(self):
        resp = self._client_for(self.outsider).get('/api/projects/')
        self.assertEqual(resp.status_code, 200)
        ids = [p['id'] for p in resp.data.get('results', resp.data)]
        self.assertNotIn(self.project.id, ids)
