"""app_automation 应用烟雾测试。

重点验证:
  - AppProject 默认值
  - AppElement.increment_usage(P1 原子自增,防并发丢计数)
  - AppScheduledTask.update_run_stats(P1 原子自增)
  - AppTestSuiteCase 唯一约束
"""
from django.test import TestCase as DjangoTestCase

from apps.users.models import User
from apps.app_automation.models import (
    AppProject, AppElement, AppScheduledTask, AppTestCase,
    AppTestSuite, AppTestSuiteCase, AppDevice, AppPackage,
)


class AppProjectTest(DjangoTestCase):
    def test_create_defaults(self):
        owner = User.objects.create_user(username='u', password='x')
        p = AppProject.objects.create(name='P', owner=owner)
        self.assertEqual(p.status, 'IN_PROGRESS')


class AppElementUsageTest(DjangoTestCase):
    """P1 修复验证:AppElement.increment_usage 使用 F() 表达式原子自增。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)
        self.element = AppElement.objects.create(
            project=self.project,
            name='登录按钮',
            element_type='BUTTON',
            created_by=self.owner,
        )

    def test_increment_usage_is_atomic(self):
        self.assertEqual(self.element.usage_count, 0)
        for _ in range(3):
            self.element.increment_usage()
        self.element.refresh_from_db()
        self.assertEqual(self.element.usage_count, 3)


class AppScheduledTaskStatsTest(DjangoTestCase):
    """P1 修复验证:AppScheduledTask.update_run_stats 原子更新,防并发丢失。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.project = AppProject.objects.create(name='P', owner=self.owner)
        self.task = AppScheduledTask.objects.create(
            name='每日跑',
            task_type='TEST_CASE',
            trigger_type='ONCE',
            project=self.project,
            created_by=self.owner,
        )

    def test_update_run_stats_success(self):
        self.task.update_run_stats(success=True)
        self.task.refresh_from_db()
        self.assertEqual(self.task.total_runs, 1)
        self.assertEqual(self.task.successful_runs, 1)
        self.assertEqual(self.task.failed_runs, 0)
        self.assertIsNotNone(self.task.last_run_time)

    def test_update_run_stats_failure(self):
        self.task.update_run_stats(success=False)
        self.task.refresh_from_db()
        self.assertEqual(self.task.failed_runs, 1)
        self.assertEqual(self.task.successful_runs, 0)

    def test_update_run_stats_multiple(self):
        for _ in range(5):
            self.task.update_run_stats(success=True)
        self.task.refresh_from_db()
        self.assertEqual(self.task.total_runs, 5)
        self.assertEqual(self.task.successful_runs, 5)


class AppTestSuiteCaseTest(DjangoTestCase):
    """唯一约束:test_suite + test_case 不能重复关联。"""

    def test_unique_suite_case(self):
        owner = User.objects.create_user(username='u', password='x')
        project = AppProject.objects.create(name='P', owner=owner)
        case = AppTestCase.objects.create(
            name='C', project=project, created_by=owner,
        )
        suite = AppTestSuite.objects.create(
            name='S', project=project, created_by=owner,
        )
        AppTestSuiteCase.objects.create(test_suite=suite, test_case=case, order=1)
        with self.assertRaises(Exception):
            AppTestSuiteCase.objects.create(test_suite=suite, test_case=case, order=2)
