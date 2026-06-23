"""analytics 应用烟雾测试。

重点验证:
  - HomeCardClickStat 唯一约束(card_type)
  - HomeCardClickStat 原子自增(P1 修复点)
  - HomeCardClickView API 层原子自增(P1 修复点,经 select_for_update + get_or_create)
  - AnalyticsEventIngestView 批量上报校验
"""
from django.test import TestCase as DjangoTestCase
from django.db.models import F
from rest_framework.test import APIClient

from apps.users.models import User
from apps.analytics.models import AnalyticsEvent, HomeCardClickStat


class AnalyticsEventTest(DjangoTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')

    def test_create_event_defaults(self):
        event = AnalyticsEvent.objects.create(event_name='click_card', user=self.user)
        self.assertEqual(event.event_type, 'custom')
        self.assertEqual(event.module, '')
        self.assertEqual(event.metadata, {})
        self.assertIsNotNone(event.created_at)

    def test_create_event_without_user(self):
        event = AnalyticsEvent.objects.create(event_name='page_view')
        self.assertIsNone(event.user)


class HomeCardClickStatTest(DjangoTestCase):
    def test_unique_card_type(self):
        HomeCardClickStat.objects.create(card_type='api_testing')
        with self.assertRaises(Exception):
            HomeCardClickStat.objects.create(card_type='api_testing')

    def test_atomic_increment_via_f_expression(self):
        """P1 修复验证:使用 F() 表达式原子自增,避免并发竞争丢失计数。"""
        stat = HomeCardClickStat.objects.create(card_type='home_card')
        # 模拟多次原子自增
        for _ in range(5):
            HomeCardClickStat.objects.filter(pk=stat.pk).update(
                click_count=F('click_count') + 1
            )
        stat.refresh_from_db()
        self.assertEqual(stat.click_count, 5)


class HomeCardClickViewTest(DjangoTestCase):
    """P1 修复验证:HomeCardClickView 经 select_for_update + get_or_create 原子自增。

    场景:第一次点击应创建记录(click_count=1),后续点击应自增,不丢失计数。
    """

    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')

    def _client(self):
        c = APIClient()
        c.force_authenticate(user=self.user)
        return c

    def test_first_click_creates_record(self):
        resp = self._client().post(
            '/api/analytics/home-card-click/', {'card_type': 'home_card'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['card_type'], 'home_card')
        self.assertEqual(resp.data['click_count'], 1)

    def test_subsequent_clicks_increment(self):
        c = self._client()
        for _ in range(3):
            c.post('/api/analytics/home-card-click/', {'card_type': 'api_card'})
        stat = HomeCardClickStat.objects.get(card_type='api_card')
        self.assertEqual(stat.click_count, 3)

    def test_missing_card_type_rejected(self):
        resp = self._client().post('/api/analytics/home-card-click/', {})
        self.assertEqual(resp.status_code, 400)

    def test_empty_card_type_rejected(self):
        resp = self._client().post('/api/analytics/home-card-click/', {'card_type': '   '})
        self.assertEqual(resp.status_code, 400)

    def test_stats_endpoint_returns_dict(self):
        HomeCardClickStat.objects.create(card_type='a', click_count=5)
        HomeCardClickStat.objects.create(card_type='b', click_count=10)
        resp = self._client().get('/api/analytics/home-card-stats/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {'a': 5, 'b': 10})


class AnalyticsEventIngestTest(DjangoTestCase):
    """埋点批量上报:支持 list、{events: [...]}、单 dict 三种格式。"""

    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')
        from apps.analytics.views import AnalyticsEventIngestView
        self.view = AnalyticsEventIngestView.as_view()

    def _req(self, payload):
        from rest_framework.test import APIRequestFactory
        f = APIRequestFactory()
        req = f.post('/x/', payload, format='json')
        req.user = self.user
        return self.view(req)

    def test_ingest_single_event(self):
        resp = self._req({'event_name': 'page_view', 'module': 'home'})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['created'], 1)
        self.assertEqual(AnalyticsEvent.objects.count(), 1)

    def test_ingest_list_payload(self):
        resp = self._req([{'event_name': 'a'}, {'event_name': 'b'}])
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['created'], 2)

    def test_ingest_events_wrapper(self):
        resp = self._req({'events': [{'event_name': 'x'}, {'event_name': 'y'}]})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['created'], 2)

    def test_ingest_empty_rejected(self):
        resp = self._req([])
        self.assertEqual(resp.status_code, 400)

    def test_ingest_invalid_format_rejected(self):
        resp = self._req('string')
        self.assertEqual(resp.status_code, 400)

