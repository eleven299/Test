"""testcases 应用烟雾测试。"""
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.projects.models import Project
from apps.testcases.models import TestCase, TestCaseStep


class TestCaseModelTest(DjangoTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)

    def test_create_defaults(self):
        case = TestCase.objects.create(
            project=self.project,
            title='登录校验',
            expected_result='成功登录',
            author=self.owner,
        )
        self.assertEqual(case.priority, 'medium')
        self.assertEqual(case.status, 'draft')
        self.assertEqual(case.test_type, 'functional')
        self.assertFalse(case.is_ai_generated)

    def test_step_unique_number(self):
        case = TestCase.objects.create(
            project=self.project, title='T', expected_result='ok', author=self.owner
        )
        TestCaseStep.objects.create(testcase=case, step_number=1, action='打开', expected='看到')
        with self.assertRaises(Exception):
            TestCaseStep.objects.create(testcase=case, step_number=1, action='重复', expected='失败')


class TestCaseAccessTest(DjangoTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.outsider = User.objects.create_user(username='out', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)
        self.case = TestCase.objects.create(
            project=self.project, title='T', expected_result='ok', author=self.owner
        )

    def test_outsider_cannot_list(self):
        c = APIClient()
        c.force_authenticate(user=self.outsider)
        resp = c.get('/api/testcases/')
        self.assertEqual(resp.status_code, 200)
        ids = [t['id'] for t in resp.data.get('results', resp.data)]
        self.assertNotIn(self.case.id, ids)

    def test_owner_can_list(self):
        c = APIClient()
        c.force_authenticate(user=self.owner)
        resp = c.get('/api/testcases/')
        self.assertEqual(resp.status_code, 200)
        ids = [t['id'] for t in resp.data.get('results', resp.data)]
        self.assertIn(self.case.id, ids)
