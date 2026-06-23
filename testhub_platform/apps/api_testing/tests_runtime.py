"""api_testing 引擎运行时单元测试。

覆盖变量、提取器、脚本沙箱、断言、引擎执行 + DDT 数据集归一化。
"""
import json
from unittest import mock

from django.test import TestCase

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


# ================ DDT 数据集归一化 ================

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
