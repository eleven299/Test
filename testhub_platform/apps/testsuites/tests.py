"""testsuites 应用烟雾测试。"""
from django.test import TestCase as DjangoTestCase

from apps.users.models import User
from apps.projects.models import Project
from apps.testcases.models import TestCase as TestCaseModel
from apps.testsuites.models import TestSuite, TestSuiteCase


class TestSuiteModelTest(DjangoTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)
        self.case = TestCaseModel.objects.create(
            project=self.project, title='T', expected_result='ok', author=self.owner
        )

    def test_create_suite(self):
        suite = TestSuite.objects.create(project=self.project, name='S1', author=self.owner)
        self.assertEqual(suite.name, 'S1')

    def test_link_case_unique(self):
        suite = TestSuite.objects.create(project=self.project, name='S2', author=self.owner)
        TestSuiteCase.objects.create(testsuite=suite, testcase=self.case, order=1)
        with self.assertRaises(Exception):
            TestSuiteCase.objects.create(testsuite=suite, testcase=self.case, order=2)

    def test_case_ordering(self):
        suite = TestSuite.objects.create(project=self.project, name='S3', author=self.owner)
        case2 = TestCaseModel.objects.create(
            project=self.project, title='T2', expected_result='ok', author=self.owner
        )
        TestSuiteCase.objects.create(testsuite=suite, testcase=case2, order=2)
        TestSuiteCase.objects.create(testsuite=suite, testcase=self.case, order=1)
        ordered = [c.testcase_id for c in suite.testsuitecase_set.all()]
        self.assertEqual(ordered, [self.case.id, case2.id])
