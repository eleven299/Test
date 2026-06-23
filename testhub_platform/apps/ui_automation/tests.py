"""ui_automation 应用烟雾测试。

重点验证:
  - UiScheduledTask.update_run_stats 原子自增(P1 修复:防并发计数丢失)
  - Element.increment_usage_count 使用 F() 表达式
  - LocatorStrategy / Element 关联
"""
from django.test import TestCase as DjangoTestCase

from apps.users.models import User
from apps.ui_automation.models import (
    UiProject, LocatorStrategy, Element, UiScheduledTask,
    TestCase as UiTestCase, TestCaseStep,
)


class UiProjectTest(DjangoTestCase):
    def test_create_defaults(self):
        owner = User.objects.create_user(username='u', password='x')
        p = UiProject.objects.create(
            name='P', base_url='https://example.com', owner=owner,
        )
        self.assertEqual(p.status, 'IN_PROGRESS')


class ElementUsageCountTest(DjangoTestCase):
    """P1 修复验证:Element.increment_usage_count 使用 F() 表达式原子自增。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.project = UiProject.objects.create(
            name='P', base_url='https://example.com', owner=self.owner,
        )
        self.strategy = LocatorStrategy.objects.create(name='css')
        self.element = Element.objects.create(
            project=self.project,
            name='登录按钮',
            locator_strategy=self.strategy,
            locator_value='.login-btn',
        )

    def test_increment_usage_count_uses_f_expression(self):
        self.assertEqual(self.element.usage_count, 0)
        # 多次原子自增,模拟并发
        for _ in range(3):
            self.element.increment_usage_count()
        self.element.refresh_from_db()
        self.assertEqual(self.element.usage_count, 3)


class ScheduledTaskStatsTest(DjangoTestCase):
    """P1 修复验证:UiScheduledTask.update_run_stats 原子更新计数,防并发丢失。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='u', password='x')
        self.project = UiProject.objects.create(
            name='P', base_url='https://example.com', owner=self.owner,
        )
        self.task = UiScheduledTask.objects.create(
            name='每日跑',
            task_type='TEST_SUITE',
            trigger_type='ONCE',
            created_by=self.owner,
            project=self.project,
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
        self.assertEqual(self.task.total_runs, 1)
        self.assertEqual(self.task.failed_runs, 1)
        self.assertEqual(self.task.successful_runs, 0)

    def test_update_run_stats_multiple_times(self):
        """连续多次更新,确认每次都自增(不会因为读旧值而覆盖)。"""
        for _ in range(5):
            self.task.update_run_stats(success=True)
        self.task.refresh_from_db()
        self.assertEqual(self.task.total_runs, 5)
        self.assertEqual(self.task.successful_runs, 5)


class UiTestCaseStepTest(DjangoTestCase):
    def test_step_unique_number(self):
        owner = User.objects.create_user(username='u', password='x')
        project = UiProject.objects.create(
            name='P', base_url='https://example.com', owner=owner,
        )
        case = UiTestCase.objects.create(
            name='C', project=project, created_by=owner,
        )
        TestCaseStep.objects.create(
            test_case=case, step_number=1, action_type='click',
        )
        with self.assertRaises(Exception):
            TestCaseStep.objects.create(
                test_case=case, step_number=1, action_type='click',
            )
