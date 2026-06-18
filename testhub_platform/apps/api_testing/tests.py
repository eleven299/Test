"""
接口自动化测试 P0 引擎单元测试

覆盖:
  - VariableContext 五级作用域与迭代栈
  - VariableExtractor(json_body / header / status_code / regex)
  - PythonScriptRuntime 正常执行与安全拦截
  - assertions 旧格式转换与各操作符
  - engine.execute_request(mock requests)
"""
import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.api_testing.context import VariableContext
from apps.api_testing.extractors import VariableExtractor, ExtractionError
from apps.api_testing.script_runtime import (
    PythonScriptRuntime, ScriptSecurityError, validate_script,
)
from apps.api_testing.assertions import (
    run_assertions, all_passed, Operator, _normalize_assertion,
)
from apps.api_testing import engine as engine_module


# ================ 辅助:伪造响应对象 ================

class FakeResponse:
    """duck-type 兼容 requests.Response 的最小实现"""
    def __init__(self, status_code=200, text='', headers=None, json_body=None):
        self.status_code = status_code
        self._text = text
        self._json_body = json_body
        self.headers = headers or {}

    @property
    def text(self):
        return self._text

    @property
    def content(self):
        return self._text.encode('utf-8')

    def json(self):
        if self._json_body is None:
            raise ValueError("No JSON")
        return self._json_body


# ================ VariableContext ================

class VariableContextTest(TestCase):

    def test_priority_high_overrides_low(self):
        ctx = VariableContext()
        ctx.set('token', 'global_val', scope='global')
        ctx.set('token', 'env_val', scope='environment')
        ctx.set('token', 'extracted_val', scope='extracted')
        self.assertEqual(ctx.get('token'), 'extracted_val')

        ctx.set('token', 'iter_val', scope='iteration')
        self.assertEqual(ctx.get('token'), 'iter_val')

        ctx.set('token', 'req_val', scope='request')
        self.assertEqual(ctx.get('token'), 'req_val')

    def test_merged_reflects_priority(self):
        ctx = VariableContext()
        ctx.load_globals({'g': 1})
        ctx.load_environment({'e': 2, 'shared': 'env'})
        ctx.set('shared', 'extracted', scope='extracted')
        merged = ctx.merged()
        self.assertEqual(merged['g'], 1)
        self.assertEqual(merged['e'], 2)
        self.assertEqual(merged['shared'], 'extracted')

    def test_iteration_stack_push_pop(self):
        ctx = VariableContext()
        ctx.set('user', 'default', scope='iteration')
        ctx.push_iteration({'user': 'alice'}, iter_index=0)
        self.assertEqual(ctx.get('user'), 'alice')
        self.assertEqual(ctx.iteration_index, 0)

        ctx.push_iteration({'user': 'bob'}, iter_index=1)
        self.assertEqual(ctx.get('user'), 'bob')
        self.assertEqual(ctx.iteration_index, 1)

        ctx.pop_iteration()
        self.assertEqual(ctx.get('user'), 'alice')
        ctx.pop_iteration()
        self.assertEqual(ctx.get('user'), 'default')

    def test_invalid_scope_raises(self):
        ctx = VariableContext()
        with self.assertRaises(ValueError):
            ctx.set('x', 1, scope='invalid_scope')

    def test_clear_request_scope(self):
        ctx = VariableContext()
        ctx.set('temp', 'abc', scope='request')
        self.assertEqual(ctx.get('temp'), 'abc')
        ctx.clear_request_scope()
        self.assertIsNone(ctx.get('temp'))


# ================ VariableExtractor ================

class VariableExtractorTest(TestCase):

    def setUp(self):
        self.ctx = VariableContext()
        self.extractor = VariableExtractor()

    def test_extract_from_json_body(self):
        resp = FakeResponse(
            status_code=200,
            text='{"data": {"token": "abc123"}}',
            headers={'content-type': 'application/json'},
            json_body={'data': {'token': 'abc123'}},
        )
        rules = [{'name': 'token', 'source': 'json_body',
                   'expression': '$.data.token'}]
        extracted = self.extractor.extract(resp, rules, self.ctx)
        self.assertEqual(extracted['token'], 'abc123')
        self.assertEqual(self.ctx.get('token'), 'abc123')

    def test_extract_from_header_case_insensitive(self):
        resp = FakeResponse(
            status_code=200,
            text='',
            headers={'X-User-Id': '42'},
        )
        rules = [{'name': 'uid', 'source': 'header',
                   'expression': 'x-user-id'}]
        extracted = self.extractor.extract(resp, rules, self.ctx)
        self.assertEqual(extracted['uid'], '42')

    def test_extract_from_status_code(self):
        resp = FakeResponse(status_code=201, text='')
        rules = [{'name': 'code', 'source': 'status_code'}]
        extracted = self.extractor.extract(resp, rules, self.ctx)
        self.assertEqual(extracted['code'], 201)

    def test_extract_from_regex(self):
        resp = FakeResponse(text='order-12345-detail')
        rules = [{'name': 'oid', 'source': 'regex',
                   'expression': r'order-(\d+)', 'group': 1}]
        extracted = self.extractor.extract(resp, rules, self.ctx)
        self.assertEqual(extracted['oid'], '12345')

    def test_extract_failure_uses_default(self):
        resp = FakeResponse(text='no match here')
        rules = [{'name': 'missing', 'source': 'regex',
                   'expression': r'nonexistent-(\d+)', 'default': 'fallback'}]
        extracted = self.extractor.extract(resp, rules, self.ctx)
        self.assertEqual(extracted['missing'], 'fallback')
        self.assertEqual(self.ctx.get('missing'), 'fallback')

    def test_extract_failure_logs(self):
        resp = FakeResponse(text='no match')
        rules = [{'name': 'missing', 'source': 'regex',
                   'expression': r'nonexistent-(\d+)'}]
        self.extractor.extract(resp, rules, self.ctx)
        self.assertTrue(any(log.get('event') == 'extract_failed'
                             for log in self.ctx.logs))


# ================ PythonScriptRuntime ================

class PythonScriptRuntimeTest(TestCase):

    def setUp(self):
        self.ctx = VariableContext()
        self.runtime = PythonScriptRuntime()

    def test_normal_script_sets_var(self):
        script = "ctx.vars.greeting = 'hello world'"
        result = self.runtime.execute(script, self.ctx)
        self.assertIsNone(result['error'])
        self.assertEqual(self.ctx.get('greeting'), 'hello world')

    def test_injected_modules_accessible(self):
        script = (
            "ctx.vars.ts = int(time.time())\n"
            "ctx.vars.h = hashlib.md5(b'abc').hexdigest()\n"
            "ctx.vars.j = json.dumps({'k': 1})\n"
        )
        result = self.runtime.execute(script, self.ctx)
        self.assertIsNone(result['error'])
        self.assertGreater(self.ctx.get('ts'), 0)
        self.assertEqual(len(self.ctx.get('h')), 32)
        self.assertEqual(self.ctx.get('j'), '{"k": 1}')

    def test_block_import_os(self):
        script = "import os\nctx.vars.x = os.listdir('/')"
        result = self.runtime.execute(script, self.ctx)
        self.assertIsNotNone(result['error'])
        self.assertIn('安全拦截', result['error'])
        # 变量不应被设置
        self.assertIsNone(self.ctx.get('x'))

    def test_block_dunder_access(self):
        script = "ctx.vars.cls = ctx.__class__"
        result = self.runtime.execute(script, self.ctx)
        self.assertIsNotNone(result['error'])

    def test_block_eval(self):
        script = "ctx.vars.r = eval('1+1')"
        result = self.runtime.execute(script, self.ctx)
        self.assertIsNotNone(result['error'])

    def test_block_open(self):
        script = "ctx.vars.f = open('/etc/passwd')"
        result = self.runtime.execute(script, self.ctx)
        self.assertIsNotNone(result['error'])

    def test_empty_script_no_op(self):
        result = self.runtime.execute('', self.ctx)
        self.assertIsNone(result['error'])
        result = self.runtime.execute('   \n  ', self.ctx)
        self.assertIsNone(result['error'])

    def test_script_exception_recorded(self):
        script = "ctx.vars.x = 1 / 0"
        result = self.runtime.execute(script, self.ctx)
        self.assertIsNotNone(result['error'])
        self.assertIn('ZeroDivisionError', result['error'])


# ================ assertions ================

class AssertionNormalizationTest(TestCase):

    def test_legacy_status_code(self):
        norm = _normalize_assertion({'type': 'status_code', 'expected': 200})
        self.assertEqual(norm['source'], 'status_code')
        self.assertEqual(norm['operator'], Operator.EQUALS)
        self.assertEqual(norm['expected'], 200)

    def test_legacy_json_path(self):
        norm = _normalize_assertion({
            'type': 'json_path',
            'json_path': '$.code',
            'expected': 0,
        })
        self.assertEqual(norm['source'], 'json_body')
        self.assertEqual(norm['operator'], Operator.EQUALS)
        self.assertEqual(norm['expression'], '$.code')
        self.assertEqual(norm['expected'], 0)

    def test_new_format_passthrough(self):
        assertion = {
            'source': 'json_body',
            'expression': '$.data.id',
            'operator': Operator.GREATER_THAN,
            'expected': 100,
        }
        norm = _normalize_assertion(assertion)
        self.assertEqual(norm, assertion)


class AssertionRunTest(TestCase):

    def test_status_code_equals_pass(self):
        resp = FakeResponse(status_code=200, text='')
        results = run_assertions(resp, [
            {'type': 'status_code', 'expected': 200},
        ])
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['passed'])

    def test_status_code_not_equals(self):
        resp = FakeResponse(status_code=200, text='')
        results = run_assertions(resp, [
            {'source': 'status_code', 'operator': Operator.NOT_EQUALS,
             'expected': 404},
        ])
        self.assertTrue(results[0]['passed'])

    def test_json_path_greater_than(self):
        resp = FakeResponse(
            status_code=200,
            text='{"price": 99}',
            headers={'content-type': 'application/json'},
            json_body={'price': 99},
        )
        results = run_assertions(resp, [
            {'source': 'json_body', 'expression': '$.price',
             'operator': Operator.GREATER_THAN, 'expected': 50},
        ])
        self.assertTrue(results[0]['passed'])

    def test_contains_string(self):
        resp = FakeResponse(text='hello world')
        results = run_assertions(resp, [
            {'source': 'raw_body', 'operator': Operator.CONTAINS,
             'expected': 'world'},
        ])
        self.assertTrue(results[0]['passed'])

    def test_regex_match(self):
        resp = FakeResponse(text='Order #12345 confirmed')
        results = run_assertions(resp, [
            {'source': 'raw_body', 'operator': Operator.REGEX,
             'expected': r'Order #\d+'},
        ])
        self.assertTrue(results[0]['passed'])

    def test_in_array(self):
        resp = FakeResponse(status_code=200, text='')
        results = run_assertions(resp, [
            {'source': 'status_code', 'operator': Operator.IN_ARRAY,
             'expected': [200, 201, 204]},
        ])
        self.assertTrue(results[0]['passed'])

    def test_type_is(self):
        resp = FakeResponse(
            status_code=200,
            text='{"count": 5}',
            headers={'content-type': 'application/json'},
            json_body={'count': 5},
        )
        results = run_assertions(resp, [
            {'source': 'json_body', 'expression': '$.count',
             'operator': Operator.TYPE_IS, 'expected': 'int'},
        ])
        self.assertTrue(results[0]['passed'])

    def test_all_passed_helper(self):
        resp = FakeResponse(status_code=200, text='ok')
        results = run_assertions(resp, [
            {'source': 'status_code', 'operator': Operator.EQUALS, 'expected': 200},
            {'source': 'raw_body', 'operator': Operator.CONTAINS, 'expected': 'ok'},
        ])
        self.assertTrue(all_passed(results))

    def test_failure_recorded(self):
        resp = FakeResponse(status_code=500, text='')
        results = run_assertions(resp, [
            {'type': 'status_code', 'expected': 200},
        ])
        self.assertFalse(results[0]['passed'])
        self.assertIsNotNone(results[0]['error'])


# ================ engine.execute_request(mock requests) ================

class EngineExecuteRequestTest(TestCase):
    """通过 mock requests.request 测试 engine.execute_request 的变量解析与请求构造"""

    def _make_api_request(self, **overrides):
        """构造内存中的 ApiRequest-like 对象(不写库)"""
        from apps.api_testing.models import ApiRequest
        req = ApiRequest(
            name=overrides.get('name', 'test'),
            method=overrides.get('method', 'GET'),
            url=overrides.get('url', 'https://api.example.com/users/{{user_id}}'),
            request_type=overrides.get('request_type', 'HTTP'),
            headers=overrides.get('headers', []),
            params=overrides.get('params', {}),
            body=overrides.get('body', {}),
            timeout=overrides.get('timeout', 30),
            skip_ssl_verify=overrides.get('skip_ssl_verify', False),
        )
        return req

    def test_variable_substitution_in_url(self):
        ctx = VariableContext()
        ctx.set('user_id', 42, scope='environment')

        api_req = self._make_api_request(url='https://api.example.com/users/{{user_id}}')

        with mock.patch.object(engine_module.requests_lib, 'request') as mock_req:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = '{"id": 42}'
            mock_resp.headers = {'content-type': 'application/json'}
            mock_resp.json.return_value = {'id': 42}
            mock_req.return_value = mock_resp

            response, elapsed, error, resolved, raw = engine_module.execute_request(
                api_req, ctx, timeout=5,
            )

        self.assertIsNone(error)
        # 验证 URL 被正确替换
        called_kwargs = mock_req.call_args.kwargs
        self.assertEqual(called_kwargs['url'], 'https://api.example.com/users/42')

    def test_dynamic_function_resolution(self):
        """${md5(xxx)} 这类动态函数应该被解析"""
        ctx = VariableContext()
        api_req = self._make_api_request(
            method='POST',
            url='https://api.example.com/sign',
            headers=[{'key': 'X-Sign', 'value': '${md5(abc)}', 'enabled': True}],
            body={'type': 'json', 'data': {'token': '${timestamp()}'}},
        )

        with mock.patch.object(engine_module.requests_lib, 'request') as mock_req:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = '{}'
            mock_resp.headers = {}
            mock_resp.json.return_value = {}
            mock_req.return_value = mock_resp

            response, elapsed, error, resolved, raw = engine_module.execute_request(
                api_req, ctx, timeout=5,
            )

        self.assertIsNone(error)
        called_kwargs = mock_req.call_args.kwargs
        # md5('abc') = 900150983cd24fb0d6963f7d28e17f72
        self.assertEqual(called_kwargs['headers']['X-Sign'],
                         '900150983cd24fb0d6963f7d28e17f72')
        # timestamp 是动态值,只断言它是数字字符串
        self.assertTrue(called_kwargs['json']['token'].isdigit())

    def test_failure_returns_error_string(self):
        ctx = VariableContext()
        api_req = self._make_api_request(url='https://api.example.com/x')

        with mock.patch.object(engine_module.requests_lib, 'request') as mock_req:
            mock_req.side_effect = engine_module.requests_lib.Timeout("timeout")

            response, elapsed, error, resolved, raw = engine_module.execute_request(
                api_req, ctx, timeout=1,
            )

        self.assertIsNone(response)
        self.assertIsNone(elapsed)
        self.assertIn('超时', error)

    def test_disabled_header_skipped(self):
        ctx = VariableContext()
        api_req = self._make_api_request(headers=[
            {'key': 'Enabled-Header', 'value': 'yes', 'enabled': True},
            {'key': 'Disabled-Header', 'value': 'no', 'enabled': False},
        ])

        with mock.patch.object(engine_module.requests_lib, 'request') as mock_req:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = ''
            mock_resp.headers = {}
            mock_resp.json.return_value = {}
            mock_req.return_value = mock_resp

            engine_module.execute_request(api_req, ctx, timeout=5)

        called_kwargs = mock_req.call_args.kwargs
        self.assertEqual(called_kwargs['headers']['Enabled-Header'], 'yes')
        self.assertNotIn('Disabled-Header', called_kwargs['headers'])


# ================ P1: Reporter(JUnit / JSON) ================

from django.contrib.auth import get_user_model as _get_user_model
from apps.api_testing.models import (
    ApiProject, ApiRequest, TestSuite, TestSuiteRequest,
    TestExecution, TestStepResult,
)
from apps.api_testing.reporters import build_junit_xml, build_json_report, build_report
from xml.etree import ElementTree as ET


UserModel = _get_user_model()


class DdtDataSetNormalizationTest(TestCase):
    """验证 _normalize_data_set 对各类输入的容错"""

    def test_empty_list_returns_single_empty_row(self):
        self.assertEqual(
            engine_module.TestExecutionEngine._normalize_data_set([]),
            [{}],
        )

    def test_none_returns_single_empty_row(self):
        self.assertEqual(
            engine_module.TestExecutionEngine._normalize_data_set(None),
            [{}],
        )

    def test_dict_with_rows_key_unwrapped(self):
        rows = [{'a': 1}, {'a': 2}]
        self.assertEqual(
            engine_module.TestExecutionEngine._normalize_data_set({'rows': rows}),
            rows,
        )

    def test_plain_dict_treated_as_single_row(self):
        self.assertEqual(
            engine_module.TestExecutionEngine._normalize_data_set({'a': 1, 'b': 2}),
            [{'a': 1, 'b': 2}],
        )

    def test_non_dict_rows_wrapped_with_value(self):
        self.assertEqual(
            engine_module.TestExecutionEngine._normalize_data_set(['x', 'y']),
            [{'value': 'x'}, {'value': 'y'}],
        )


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


# ================ P1: CLI run_api_suite ================

from io import StringIO
from django.core.management import call_command


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
