"""api_testing 报告与 CLI 单元测试。

覆盖:
  - JUnit / JSON Reporter 输出格式
  - run_api_suite 管理命令(退出码 / 报告文件)
  - /api/api-testing/test-executions/{id}/export-report/ 端到端
"""
import json
from datetime import timedelta
from io import StringIO
from unittest import mock
from xml.etree import ElementTree as ET

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.api_testing import engine as engine_module
from apps.api_testing.models import (
    ApiProject, ApiRequest, TestSuite, TestSuiteRequest,
    TestExecution, TestStepResult,
)
from apps.api_testing.reporters import (
    build_junit_xml, build_json_report, build_report,
)


UserModel = get_user_model()


# ================ Reporter 测试基类 ================

class _ReporterTestBase(TestCase):
    """Reporter 测试基类:构造一个套件 + 执行记录 + 步骤结果"""

    @classmethod
    def setUpTestData(cls):
        cls.user = UserModel.objects.create_user(
            username='reporter_tester', password='x', email='t@e.com',
        )
        cls.project = ApiProject.objects.create(
            name='Reporter 测试项目', project_type='HTTP', status='IN_PROGRESS',
            owner=cls.user,
        )
        cls.suite = TestSuite.objects.create(
            project=cls.project, name='Reporter 套件',
            created_by=cls.user,
        )
        cls.req1 = ApiRequest.objects.create(
            name='登录', method='POST', url='https://x/login',
            headers=[], params={}, body={},
            created_by=cls.user,
        )
        cls.req2 = ApiRequest.objects.create(
            name='获取详情', method='GET', url='https://x/detail/{{id}}',
            headers=[], params={}, body={},
            created_by=cls.user,
        )
        cls.step1 = TestSuiteRequest.objects.create(
            test_suite=cls.suite, request=cls.req1, order=1,
        )
        cls.step2 = TestSuiteRequest.objects.create(
            test_suite=cls.suite, request=cls.req2, order=2,
        )

    def _make_execution(self, *, with_steps=True, step1_status='passed',
                          step2_status='failed', execution_status='FAILED'):
        execution = TestExecution.objects.create(
            test_suite=self.suite,
            status=execution_status,
            start_time=timezone.now() - timedelta(seconds=10),
            end_time=timezone.now(),
            total_requests=2,
            passed_requests=1 if step1_status == 'passed' else 0,
            failed_requests=1 if step2_status == 'failed' else 0,
            executed_by=self.user,
            trigger_source='cli',
        )
        if with_steps:
            TestStepResult.objects.create(
                execution=execution, suite_request=self.step1, request=self.req1,
                request_name=self.req1.name, method=self.req1.method, url=self.req1.url,
                status=step1_status, status_code=200, response_time=123.4,
                attempt=1,
                assertions_results=[{'name': 'code', 'passed': True,
                                      'source': 'status_code', 'operator': 'equals',
                                      'expected': 200, 'actual': 200}],
                started_at=timezone.now() - timedelta(seconds=5),
                finished_at=timezone.now() - timedelta(seconds=4),
            )
            TestStepResult.objects.create(
                execution=execution, suite_request=self.step2, request=self.req2,
                request_name=self.req2.name, method=self.req2.method, url=self.req2.url,
                status=step2_status, status_code=500, response_time=456.7,
                attempt=1,
                error_message='断言失败:期望 200,实际 500',
                assertions_results=[{'name': 'code', 'passed': False,
                                      'source': 'status_code', 'operator': 'equals',
                                      'expected': 200, 'actual': 500,
                                      'error': '断言失败:期望 200,实际 500'}],
                started_at=timezone.now() - timedelta(seconds=3),
                finished_at=timezone.now(),
            )
        return execution


# ================ JUnit Reporter ================

class JUnitReporterTest(_ReporterTestBase):

    def test_xml_well_formed(self):
        execution = self._make_execution()
        xml = build_junit_xml(execution)
        # 必须能正确解析回来
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, 'testsuites')
        suite = root.find('testsuite')
        self.assertIsNotNone(suite)
        self.assertEqual(suite.get('tests'), '2')
        self.assertEqual(suite.get('failures'), '1')

    def test_passed_and_failed_cases_present(self):
        execution = self._make_execution()
        xml = build_junit_xml(execution)
        root = ET.fromstring(xml)
        cases = root.findall('.//testcase')
        self.assertEqual(len(cases), 2)
        # 第一个无 failure(通过)
        self.assertIsNone(cases[0].find('failure'))
        # 第二个有 failure
        self.assertIsNotNone(cases[1].find('failure'))

    def test_error_status_emits_error_node(self):
        execution = self._make_execution(step1_status='error', step2_status='error',
                                          execution_status='FAILED')
        xml = build_junit_xml(execution)
        root = ET.fromstring(xml)
        suite = root.find('testsuite')
        self.assertEqual(suite.get('errors'), '2')
        self.assertEqual(len(root.findall('.//error')), 2)

    def test_skipped_status_emits_skipped_node(self):
        execution = self._make_execution(step1_status='passed', step2_status='skipped')
        xml = build_junit_xml(execution)
        root = ET.fromstring(xml)
        self.assertEqual(len(root.findall('.//skipped')), 1)

    def test_special_chars_escaped(self):
        execution = self._make_execution()
        # 注入特殊字符到 error_message
        s = execution.step_results.first()
        s.error_message = '<tag> & "quotes" </tag>'
        s.save()
        xml = build_junit_xml(execution)
        # 必须能正确解析回来(若未转义会抛 ParseError)
        root = ET.fromstring(xml)
        self.assertIsNotNone(root.find('.//failure'))

    def test_suite_metadata_in_properties(self):
        execution = self._make_execution()
        execution.stop_reason = 'fail-fast 触发'
        execution.save()
        xml = build_junit_xml(execution)
        root = ET.fromstring(xml)
        props = {p.get('name'): p.get('value') for p in root.findall('.//property')}
        self.assertEqual(props.get('execution_id'), str(execution.id))
        self.assertIn('fail-fast', props.get('stop_reason', ''))


# ================ JSON Reporter ================

class JsonReporterTest(_ReporterTestBase):

    def test_report_structure(self):
        execution = self._make_execution()
        report = build_json_report(execution, include_snapshots=True)
        self.assertIn('execution', report)
        self.assertIn('suite', report)
        self.assertIn('summary', report)
        self.assertIn('steps', report)
        self.assertEqual(len(report['steps']), 2)

    def test_summary_counts(self):
        execution = self._make_execution()
        report = build_json_report(execution)
        self.assertEqual(report['summary']['total'], 2)
        self.assertEqual(report['summary']['passed'], 1)
        self.assertEqual(report['summary']['failed'], 1)
        self.assertEqual(report['summary']['pass_rate'], 50.0)

    def test_no_snapshots_strips_payload(self):
        execution = self._make_execution()
        # 给步骤加 snapshot
        s = execution.step_results.first()
        s.request_snapshot = {'secret': 'value'}
        s.response_snapshot = {'body': 'long...'}
        s.save()

        with_snap = build_json_report(execution, include_snapshots=True)
        self.assertIn('request_snapshot', with_snap['steps'][0])

        without_snap = build_json_report(execution, include_snapshots=False)
        self.assertNotIn('request_snapshot', without_snap['steps'][0])

    def test_build_report_format_dispatch(self):
        execution = self._make_execution()
        json_str = build_report(execution, fmt='json')
        self.assertIsInstance(json_str, str)
        parsed = json.loads(json_str)
        self.assertEqual(parsed['execution']['id'], execution.id)

        xml_str = build_report(execution, fmt='junit')
        self.assertTrue(xml_str.startswith('<?xml'))
        self.assertEqual(xml_str, build_report(execution, fmt='xml'))

        with self.assertRaises(ValueError):
            build_report(execution, fmt='unknown_format')


# ================ CLI: run_api_suite ================

class RunApiSuiteCLITest(_ReporterTestBase):
    """通过 call_command 测试 CLI 退出码与报告输出"""

    def _patch_requests_to_succeed(self):
        """让所有 requests.request 返回 200 OK"""
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"code": 0}'
        mock_resp.headers = {'content-type': 'application/json'}
        mock_resp.json.return_value = {'code': 0}
        return mock.patch.object(engine_module.requests_lib, 'request',
                                  return_value=mock_resp)

    def _patch_requests_to_fail(self, status_code=500):
        mock_resp = mock.MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = '{"code": 1}'
        mock_resp.headers = {'content-type': 'application/json'}
        mock_resp.json.return_value = {'code': 1}
        return mock.patch.object(engine_module.requests_lib, 'request',
                                  return_value=mock_resp)

    def test_resolve_suite_by_id(self):
        from apps.api_testing.management.commands.run_api_suite import Command
        cmd = Command()
        suite = cmd._resolve_suite(str(self.suite.id))
        self.assertEqual(suite.id, self.suite.id)

    def test_resolve_suite_by_name(self):
        from apps.api_testing.management.commands.run_api_suite import Command
        cmd = Command()
        suite = cmd._resolve_suite('Reporter 套件')
        self.assertEqual(suite.id, self.suite.id)

    def test_resolve_suite_not_found(self):
        from apps.api_testing.management.commands.run_api_suite import Command
        from django.core.management.base import CommandError
        cmd = Command()
        with self.assertRaises(CommandError):
            cmd._resolve_suite('不存在的套件XYZ123')

    def test_cli_exit_zero_when_all_pass(self):
        # 把第二个接口也设置成通过的断言
        self.req2.assertions = [
            {'source': 'status_code', 'operator': 'equals', 'expected': 200}
        ]
        self.req2.save()

        with self._patch_requests_to_succeed():
            out = StringIO()
            err = StringIO()
            try:
                call_command('run_api_suite', str(self.suite.id),
                              '--output', 'json', '--no-snapshots',
                              '--trigger', 'ci',
                              stdout=out, stderr=err)
                code = 0
            except SystemExit as e:
                code = e.code
        self.assertEqual(code, 0)
        self.assertIn('总计', out.getvalue())

    def test_cli_exit_one_when_failed(self):
        # 第一个接口断言 200 但 mock 返回 500
        self.req1.assertions = [
            {'source': 'status_code', 'operator': 'equals', 'expected': 200}
        ]
        self.req1.save()
        self.req2.assertions = [
            {'source': 'status_code', 'operator': 'equals', 'expected': 200}
        ]
        self.req2.save()

        with self._patch_requests_to_fail(status_code=500):
            try:
                call_command('run_api_suite', str(self.suite.id),
                              '--quiet')
                code = 0
            except SystemExit as e:
                code = e.code
        self.assertEqual(code, 1)

    def test_cli_exit_two_when_suite_missing(self):
        try:
            call_command('run_api_suite', '99999999')
            code = 0
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 2)

    def test_cli_junit_report_to_file(self):
        import tempfile, os
        with self._patch_requests_to_succeed():
            # 让断言通过
            self.req1.assertions = [
                {'source': 'status_code', 'operator': 'equals', 'expected': 200}
            ]
            self.req1.save()
            self.req2.assertions = [
                {'source': 'status_code', 'operator': 'equals', 'expected': 200}
            ]
            self.req2.save()

            tmp = tempfile.NamedTemporaryFile(
                mode='w', suffix='.xml', delete=False, encoding='utf-8'
            )
            tmp.close()
            try:
                try:
                    call_command('run_api_suite', str(self.suite.id),
                                  '--output', 'junit',
                                  '--output-file', tmp.name,
                                  '--quiet')
                    code = 0
                except SystemExit as e:
                    code = e.code
                self.assertEqual(code, 0)

                with open(tmp.name, 'r', encoding='utf-8') as f:
                    xml = f.read()
                self.assertTrue(xml.startswith('<?xml'))
                root = ET.fromstring(xml)
                self.assertEqual(root.tag, 'testsuites')
            finally:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)


# ================ 报告导出接口 ================

class ExportReportAPITest(_ReporterTestBase):
    """GET /api/api-testing/test-executions/{id}/export-report/ 端到端测试"""

    def _client(self):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(self.user)
        return c

    def test_export_json_returns_application_json(self):
        execution = self._make_execution()
        c = self._client()
        r = c.get(f'/api/api-testing/test-executions/{execution.id}/export-report/'
                  '?fmt=json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('application/json', r['Content-Type'])
        body = json.loads(r.content.decode('utf-8'))
        self.assertEqual(body['execution']['id'], execution.id)
        self.assertEqual(body['summary']['total'], 2)
        # 默认带快照
        self.assertIn('request_snapshot', body['steps'][0])

    def test_export_json_without_snapshots(self):
        execution = self._make_execution()
        s = execution.step_results.first()
        s.request_snapshot = {'secret': 'value'}
        s.response_snapshot = {'body': 'long'}
        s.save()

        c = self._client()
        r = c.get(f'/api/api-testing/test-executions/{execution.id}/export-report/'
                  '?fmt=json&include_snapshots=0')
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content.decode('utf-8'))
        self.assertNotIn('request_snapshot', body['steps'][0])
        self.assertNotIn('response_snapshot', body['steps'][0])

    def test_export_json_download_has_attachment_header(self):
        execution = self._make_execution()
        c = self._client()
        r = c.get(f'/api/api-testing/test-executions/{execution.id}/export-report/'
                  '?fmt=json&download=1')
        self.assertEqual(r.status_code, 200)
        disp = r['Content-Disposition']
        self.assertIn('attachment', disp)
        self.assertIn('.json', disp)

    def test_export_junit_xml_well_formed(self):
        execution = self._make_execution()
        c = self._client()
        r = c.get(f'/api/api-testing/test-executions/{execution.id}/export-report/'
                  '?fmt=junit')
        self.assertEqual(r.status_code, 200)
        self.assertIn('xml', r['Content-Type'])
        root = ET.fromstring(r.content)
        self.assertEqual(root.tag, 'testsuites')
        suite = root.find('testsuite')
        self.assertEqual(suite.get('tests'), '2')
        self.assertEqual(suite.get('failures'), '1')

    def test_export_xml_alias_for_junit(self):
        """fmt=xml 应被视作 junit"""
        execution = self._make_execution()
        c = self._client()
        r = c.get(f'/api/api-testing/test-executions/{execution.id}/export-report/'
                  '?fmt=xml&download=1')
        self.assertEqual(r.status_code, 200)
        self.assertIn('.xml', r['Content-Disposition'])
        root = ET.fromstring(r.content)
        self.assertEqual(root.tag, 'testsuites')

    def test_export_junit_download_header(self):
        execution = self._make_execution()
        c = self._client()
        r = c.get(f'/api/api-testing/test-executions/{execution.id}/export-report/'
                  '?fmt=junit&download=1')
        self.assertEqual(r.status_code, 200)
        disp = r['Content-Disposition']
        self.assertIn('attachment', disp)
        self.assertIn('.xml', disp)

    def test_export_unsupported_format_returns_400(self):
        execution = self._make_execution()
        c = self._client()
        r = c.get(f'/api/api-testing/test-executions/{execution.id}/export-report/'
                  '?fmt=pdf')
        self.assertEqual(r.status_code, 400)

    def test_export_default_format_is_json(self):
        execution = self._make_execution()
        c = self._client()
        r = c.get(f'/api/api-testing/test-executions/{execution.id}/export-report/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('application/json', r['Content-Type'])

    def test_export_other_user_forbidden(self):
        """别的用户看不到本执行记录(404)"""
        from rest_framework.test import APIClient
        execution = self._make_execution()
        other = UserModel.objects.create_user(
            username='export_other', password='x', email='e@e.com',
        )
        c = APIClient()
        c.force_authenticate(other)
        r = c.get(f'/api/api-testing/test-executions/{execution.id}/export-report/'
                  '?fmt=json')
        self.assertEqual(r.status_code, 404)
