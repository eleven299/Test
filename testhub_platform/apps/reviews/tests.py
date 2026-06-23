"""reviews 应用烟雾测试。

重点验证:
  - TestCaseReview / ReviewAssignment 基本 CRUD
  - ReviewAssignment 唯一约束(review, reviewer)
  - my_reviews 防御性过滤(P0):被分配到不可访问项目的评审不应返回
"""
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.users.models import User
from apps.projects.models import Project, ProjectMember
from apps.reviews.models import TestCaseReview, ReviewAssignment


class ReviewModelTest(DjangoTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.reviewer = User.objects.create_user(username='rev', password='x')
        self.project = Project.objects.create(name='P', owner=self.owner)

    def test_create_review_defaults(self):
        review = TestCaseReview.objects.create(title='R1', creator=self.owner)
        review.projects.add(self.project)
        self.assertEqual(review.status, 'pending')
        self.assertEqual(review.priority, 'medium')

    def test_assignment_unique(self):
        review = TestCaseReview.objects.create(title='R', creator=self.owner)
        ReviewAssignment.objects.create(review=review, reviewer=self.reviewer)
        with self.assertRaises(Exception):
            ReviewAssignment.objects.create(review=review, reviewer=self.reviewer)


class MyReviewsAccessTest(DjangoTestCase):
    """验证 my_reviews 防御性过滤:即便被错误分配为 reviewer,项目不可见时也不应返回。"""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.reviewer = User.objects.create_user(username='rev', password='x')
        # reviewer 是 accessible 项目的成员,所以 'Visible' 应可见
        self.project = Project.objects.create(name='Accessible', owner=self.owner)
        ProjectMember.objects.create(project=self.project, user=self.reviewer)
        self.review_in = TestCaseReview.objects.create(title='Visible', creator=self.owner)
        self.review_in.projects.add(self.project)
        ReviewAssignment.objects.create(review=self.review_in, reviewer=self.reviewer)

        # 项目 B 是 owner 私有的,reviewer 不在 members 里
        self.private_project = Project.objects.create(name='Private', owner=self.owner)
        self.review_out = TestCaseReview.objects.create(title='Hidden', creator=self.owner)
        self.review_out.projects.add(self.private_project)
        ReviewAssignment.objects.create(review=self.review_out, reviewer=self.reviewer)

    def test_reviewer_only_sees_accessible_reviews(self):
        c = APIClient()
        c.force_authenticate(user=self.reviewer)
        resp = c.get('/api/reviews/reviews/my_reviews/')
        self.assertEqual(resp.status_code, 200)
        titles = [r['title'] for r in resp.data]
        self.assertIn('Visible', titles)
        self.assertNotIn('Hidden', titles)
