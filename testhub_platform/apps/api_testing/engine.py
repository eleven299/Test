"""
接口自动化测试 - 执行引擎(P0 核心)

提供单一执行入口,被 views / 定时任务 / CLI 共用。

主要 API:
    TestExecutionEngine(suite, environment, user, options)
        .run() -> TestExecution
    execute_request(api_request, context, *, timeout, runtime, request_snapshot)
        -> (response, response_time_ms, error)

设计原则:
    - 引擎不写 HTTP 层细节(发请求交给 execute_request)
    - 引擎不感知 Django Request/Response,所有交互通过 VariableContext
    - 步骤结果统一写入 TestStepResult 表
    - 旧 TestExecution.results 字段同步写入,保证前端兼容
"""
import logging
import time
import copy
from typing import Any, Dict, List, Optional, Tuple

import requests as requests_lib
from django.utils import timezone

from .context import VariableContext
from .extractors import VariableExtractor
from .script_runtime import PythonScriptRuntime
from .assertions import run_assertions, all_passed
from .variable_resolver import VariableResolver
from .models import (
    ApiRequest, TestSuite, TestSuiteRequest, TestExecution, TestStepResult,
    RequestHistory,
)

logger = logging.getLogger(__name__)


# ================ 变量解析辅助 ================

_VAR_PATTERN_CACHE = {}


def replace_placeholders(text: str, variables: Dict[str, Any]) -> str:
    """替换 {{var}} 占位符

    兼容 Postman 风格的 dict 变量:{key: {currentValue: x, ...}}
    """
    if not isinstance(text, str) or not text:
        return text
    result = text
    for key, value in (variables or {}).items():
        if isinstance(value, dict):
            replacement = value.get('currentValue')
            if replacement in (None, ''):
                replacement = value.get('initialValue', '')
        elif value is None:
            replacement = ''
        else:
            replacement = value
        result = result.replace(f'{{{{{key}}}}}', str(replacement))
    return result


def resolve_value(value: Any, variables: Dict[str, Any], resolver: VariableResolver) -> Any:
    """递归解析任意类型值的变量

    - dict / list 递归
    - str 先做 {{var}} 替换,再做 ${func()} 解析
    """
    if isinstance(value, dict):
        return {k: resolve_value(v, variables, resolver) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, variables, resolver) for item in value]
    if isinstance(value, str):
        replaced = replace_placeholders(value, variables)
        return resolver.resolve(replaced)
    return value


def build_headers(raw_headers: Any, variables: Dict[str, Any],
                   resolver: VariableResolver) -> Dict[str, str]:
    """构造请求头字典

    支持两种格式:
      - 列表: [{"key": "Authorization", "value": "Bearer {{token}}", "enabled": true}, ...]
      - 字典: {"Authorization": "Bearer {{token}}"}
    """
    headers: Dict[str, str] = {}
    if not raw_headers:
        return headers
    if isinstance(raw_headers, list):
        for item in raw_headers:
            if not isinstance(item, dict):
                continue
            if not item.get('enabled', True):
                continue
            key = item.get('key')
            if not key:
                continue
            value = item.get('value', '')
            resolved = resolve_value(value, variables, resolver)
            headers[str(key)] = '' if resolved is None else str(resolved)
    elif isinstance(raw_headers, dict):
        for key, value in raw_headers.items():
            resolved = resolve_value(value, variables, resolver)
            headers[str(key)] = '' if resolved is None else str(resolved)
    return headers


def build_params(raw_params: Any, variables: Dict[str, Any],
                  resolver: VariableResolver) -> Dict[str, Any]:
    """构造 query 参数

    支持列表/字典两种格式(与 headers 一致)
    """
    if isinstance(raw_params, list):
        params: Dict[str, Any] = {}
        for item in raw_params:
            if not isinstance(item, dict):
                continue
            if not item.get('enabled', True):
                continue
            key = item.get('key')
            if not key:
                continue
            value = item.get('value', '')
            resolved = resolve_value(value, variables, resolver)
            params[str(key)] = '' if resolved is None else resolved
        return params
    if isinstance(raw_params, dict):
        return {k: resolve_value(v, variables, resolver) for k, v in raw_params.items()}
    return {}


def build_body(raw_body: Any, method: str, variables: Dict[str, Any],
                resolver: VariableResolver) -> Tuple[str, Any]:
    """构造请求体

    返回: (body_type, body_data)
        body_type: 'json' / 'raw' / 'form-data' / 'x-www-form-urlencoded' / 'none'
    """
    if not raw_body or method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return 'none', None

    body_type = raw_body.get('type', 'none') if isinstance(raw_body, dict) else 'none'
    body_content = raw_body.get('data') if isinstance(raw_body, dict) else None

    if body_type == 'json':
        return 'json', resolve_value(body_content, variables, resolver)
    if body_type == 'raw':
        if isinstance(body_content, str):
            return 'raw', resolve_value(body_content, variables, resolver)
        return 'raw', body_content
    if body_type in ('form-data', 'x-www-form-urlencoded'):
        return body_type, resolve_value(body_content, variables, resolver)
    return 'none', None


# ================ 单次请求执行 ================

def execute_request(api_request: ApiRequest, context: VariableContext,
                     timeout: int = 30, skip_ssl_verify: bool = False,
                     request_snapshot: Optional[Dict[str, Any]] = None
                     ) -> Tuple[Optional[Any], Optional[float], Optional[str],
                                 Dict[str, Any], Dict[str, Any]]:
    """执行一次 HTTP / WebSocket 请求(不含断言、提取、脚本)

    Returns:
        (response, response_time_ms, error, resolved_request, raw_request_data)
        response        成功时为 requests.Response / WebSocketResponse,失败为 None
        response_time   毫秒,失败时为 None
        error           错误信息字符串,成功时为 None
        resolved_request  解析变量后的请求配置(method/url/headers/params/body_type/body)
        raw_request_data  写入 RequestHistory 的 request_data 快照
    """
    resolver = VariableResolver()
    variables = context.merged()

    method = api_request.method
    url_raw = api_request.url or ''
    url = resolver.resolve(replace_placeholders(url_raw, variables))

    headers = build_headers(api_request.headers, variables, resolver)
    params = build_params(api_request.params, variables, resolver)
    body_type, body_data = build_body(api_request.body, method, variables, resolver)

    raw_request_data = {
        'url': url,
        'method': method,
        'headers': headers,
        'params': params,
        'body': body_data,
        'body_type': body_type,
        'request_type': api_request.request_type,
    }

    # WebSocket 分支
    if (api_request.request_type or 'HTTP').upper() == 'WEBSOCKET':
        try:
            start = time.time()
            response = _send_websocket(url, headers, body_data, timeout)
            elapsed = (time.time() - start) * 1000
            return response, elapsed, None, raw_request_data, raw_request_data
        except Exception as e:
            return None, None, str(e), raw_request_data, raw_request_data

    # HTTP 分支
    try:
        kwargs: Dict[str, Any] = {
            'method': method,
            'url': url,
            'headers': headers,
            'params': params,
            'timeout': timeout,
            'verify': not skip_ssl_verify,
        }
        if body_type == 'json':
            kwargs['json'] = body_data
        elif body_type == 'raw':
            kwargs['data'] = body_data if isinstance(body_data, (str, bytes)) else str(body_data)
        elif body_type in ('form-data', 'x-www-form-urlencoded'):
            if isinstance(body_data, dict):
                kwargs['data'] = body_data
            elif isinstance(body_data, list):
                # [{key, value, enabled}, ...] 转 dict
                kwargs['data'] = {
                    item.get('key'): item.get('value')
                    for item in body_data
                    if isinstance(item, dict) and item.get('enabled', True) and item.get('key')
                }

        start = time.time()
        response = requests_lib.request(**kwargs)
        elapsed = (time.time() - start) * 1000
        return response, elapsed, None, raw_request_data, raw_request_data
    except requests_lib.Timeout as e:
        return None, None, f"请求超时(>{timeout}s): {e}", raw_request_data, raw_request_data
    except requests_lib.RequestException as e:
        return None, None, f"请求异常: {e}", raw_request_data, raw_request_data
    except Exception as e:
        return None, None, f"未知异常: {e}", raw_request_data, raw_request_data


class WebSocketResponse:
    """WebSocket 响应包装,duck-type 兼容 requests.Response

    提供统一的 .text / .json() / .headers / .status_code 接口,
    让断言与提取器无需特判。
    """
    def __init__(self, messages: List[str], status_code: int = 101):
        self.messages = messages
        self.status_code = status_code
        self.headers = {}
        self._text = '\n'.join(messages)

    @property
    def text(self) -> str:
        return self._text

    @property
    def content(self) -> bytes:
        return self._text.encode('utf-8')

    def json(self):
        import json as _json
        # 取最后一条非空消息尝试解析
        for msg in reversed(self.messages):
            if msg:
                try:
                    return _json.loads(msg)
                except Exception:
                    continue
        raise ValueError("无可解析为 JSON 的消息")


def _send_websocket(url: str, headers: Dict[str, str], body: Any,
                     timeout: int) -> WebSocketResponse:
    """发起 WebSocket 请求

    依赖 websocket-client 库,失败时抛出可读错误。
    """
    try:
        import websocket
    except ImportError as e:
        raise RuntimeError(f"WebSocket 执行需要 websocket-client: {e}")

    header_list = [f"{k}: {v}" for k, v in (headers or {}).items() if v is not None]
    ws = websocket.create_connection(
        url,
        header=header_list,
        timeout=timeout,
    )
    try:
        if body is not None:
            if isinstance(body, (dict, list)):
                import json as _json
                ws.send(_json.dumps(body))
            else:
                ws.send(str(body))

        messages: List[str] = []
        # 默认接收 1 条消息;调用方可后续扩展
        try:
            messages.append(ws.recv())
        except Exception:
            pass
        return WebSocketResponse(messages)
    finally:
        ws.close()


# ================ 套件执行引擎 ================

class TestExecutionEngine:
    """接口自动化测试套件执行引擎"""

    def __init__(self, test_suite: TestSuite,
                 environment: Optional[Any] = None,
                 user: Optional[Any] = None,
                 trigger_source: str = 'manual',
                 persist_history: bool = True,
                 dataset_override: Optional[Any] = None):
        self.test_suite = test_suite
        self.environment = environment
        self.user = user
        self.trigger_source = trigger_source
        self.persist_history = persist_history
        self.dataset_override = dataset_override

        self.context = VariableContext()
        self.extractor = VariableExtractor()
        self.runtime = PythonScriptRuntime()
        self.stop_requested = False

        # 执行统计
        self.passed_count = 0
        self.failed_count = 0
        self.total_count = 0
        self.all_step_results: List[TestStepResult] = []
        self.legacy_results: List[Dict[str, Any]] = []

    # ---------- 主入口 ----------

    def run(self) -> TestExecution:
        """执行套件,返回 TestExecution 记录"""
        execution = TestExecution.objects.create(
            test_suite=self.test_suite,
            status='RUNNING',
            start_time=timezone.now(),
            executed_by=self.user,
            trigger_source=self.trigger_source,
        )

        # 环境快照
        env_vars = {}
        if self.environment:
            env_vars = dict(self.environment.variables or {})
        execution.environment_snapshot = {
            'environment_id': getattr(self.environment, 'id', None),
            'environment_name': getattr(self.environment, 'name', None),
            'variables': env_vars,
        }
        execution.save()

        self.context.load_environment(env_vars)
        self.context.load_globals(_collect_global_variables())
        self._current_execution = execution

        try:
            self._run_steps(execution)
            self._finalize_success(execution)
        except Exception as e:
            logger.exception("套件执行异常: %s", e)
            execution.status = 'FAILED'
            execution.stop_reason = str(e)
            self._finalize(execution)
        return execution

    # ---------- 步骤循环 ----------

    def _run_steps(self, execution: TestExecution) -> None:
        steps = list(TestSuiteRequest.objects.filter(
            test_suite=self.test_suite, enabled=True
        ).select_related('request', 'dataset').order_by('order'))

        # 计算含 DDT 迭代的总请求数
        expanded_counts = [
            len(self._normalize_data_set(self._resolve_step_data_set(s, self.dataset_override)))
            for s in steps
        ]
        self.total_count = sum(expanded_counts) if expanded_counts else 0
        execution.total_requests = self.total_count
        execution.save()

        suite_fail_fast = self.test_suite.fail_fast
        think_time_ms = max(0, self.test_suite.think_time or 0)
        default_retry = max(0, self.test_suite.default_retry_count or 0)

        for step_idx, step in enumerate(steps):
            if self.stop_requested:
                # 后续步骤标记为 skipped
                self._mark_skipped(execution, step)
                continue

            # DDT: dataset_override > step.dataset > step.data_set;都为空时单次执行(iteration=0)
            # 非空时按行迭代,每行 push 一次 iteration scope
            resolved_data_set = self._resolve_step_data_set(step, self.dataset_override)
            data_rows = self._normalize_data_set(resolved_data_set)

            for iter_idx, row_vars in enumerate(data_rows):
                if self.stop_requested:
                    break

                # 推入迭代变量到 L4 scope
                if row_vars:
                    self.context.push_iteration(row_vars, iter_index=iter_idx)

                result = self._run_step(execution, step, default_retry, iteration=iter_idx)
                self.all_step_results.append(result)

                # 旧格式结果同步写入
                self.legacy_results.append(self._to_legacy_result(step, result))

                if result.status == 'passed':
                    self.passed_count += 1
                else:
                    self.failed_count += 1

                    # fail_fast:仅关键步骤触发
                    if suite_fail_fast and step.is_critical:
                        execution.stop_reason = \
                            f"关键步骤「{step.request.name if step.request else '(已删除)'}」失败,触发 fail-fast"
                        self.stop_requested = True

                # 弹出迭代 scope
                if row_vars:
                    self.context.pop_iteration()

            # think time
            if think_time_ms > 0 and step_idx < self.total_count - 1:
                time.sleep(think_time_ms / 1000.0)

    @staticmethod
    def _normalize_data_set(raw) -> List[Dict[str, Any]]:
        """将 data_set 规整成 [{...}, ...] 形式;空或非法时返回 [{}] 即单次执行"""
        if not raw:
            return [{}]
        if isinstance(raw, dict):
            # 兼容 {"rows": [...]} 或直接视作单行
            if 'rows' in raw and isinstance(raw['rows'], list):
                raw = raw['rows']
            else:
                return [raw]
        if not isinstance(raw, list) or len(raw) == 0:
            return [{}]
        normalized = []
        for row in raw:
            if isinstance(row, dict):
                normalized.append(row)
            else:
                normalized.append({'value': row})
        return normalized

    @staticmethod
    def _resolve_step_data_set(step: TestSuiteRequest,
                                override_dataset: Optional[Any] = None):
        """合并步骤的独立数据集与内联数据集。

        合并语义(优先级从高到低):
        - override_dataset 非空且 data 非空 → 用 override_dataset.data
          (由 dataset/run 接口传入,用于"数据集批量执行"场景,不改库)
        - dataset FK 非空且 data 非空 → 用 dataset.data
        - dataset.data 为空 → 退回 inline data_set
        - dataset FK 为空 → 用 inline data_set
        - 两者都为空 → 返回 None(由 _normalize_data_set 视为单次执行)
        """
        if override_dataset is not None and isinstance(override_dataset.data, list) \
                and len(override_dataset.data) > 0:
            return override_dataset.data
        dataset = getattr(step, 'dataset', None)
        if dataset is not None and isinstance(dataset.data, list) and len(dataset.data) > 0:
            return dataset.data
        return step.data_set

    def _run_step(self, execution: TestExecution, step: TestSuiteRequest,
                   default_retry: int, iteration: int = 0) -> TestStepResult:
        """执行单个步骤(含重试 / 脚本 / 断言 / 提取)"""
        api_request = step.request
        now = timezone.now()
        result = TestStepResult(
            execution=execution,
            suite_request=step,
            request=api_request,
            request_name=api_request.name if api_request else '(已删除)',
            method=api_request.method if api_request else '',
            url=api_request.url if api_request else '',
            iteration=iteration,
            status='error',
            attempt=1,
            started_at=now,
        )

        if api_request is None:
            result.status = 'skipped'
            result.error_message = "关联的接口请求已删除"
            result.finished_at = timezone.now()
            result.save()
            return result

        # 步骤超时:step 覆盖 > 请求自身
        timeout = step.timeout_override or api_request.timeout or 30
        max_attempts = 1 + max(api_request.retry_count or 0, default_retry)
        retry_interval = max(0, api_request.retry_interval or 1)
        skip_ssl = api_request.skip_ssl_verify or False

        # 请求级重试循环
        for attempt in range(1, max_attempts + 1):
            if self.stop_requested:
                result.status = 'skipped'
                result.error_message = "套件已停止"
                break

            self.context.clear_request_scope()
            attempt_logs: List[str] = []

            # 1. 解析变量(用于快照)
            resolved_request = self._preview_resolved_request(api_request)

            # 2. 前置脚本
            if api_request.pre_request_script:
                pre_res = self.runtime.execute(
                    api_request.pre_request_script,
                    self.context,
                    request_snapshot=resolved_request,
                    response=None,
                )
                attempt_logs.extend(pre_res.get('logs') or [])
                if pre_res.get('error'):
                    result.script_logs = list(result.script_logs or []) + \
                        [{'phase': 'pre', 'error': pre_res['error']}]
                # 脚本可能修改了变量,重新解析
                resolved_request = self._preview_resolved_request(api_request)

            # 3. 发请求
            response, response_time, error, resolved_request, raw_request_data = execute_request(
                api_request, self.context,
                timeout=timeout, skip_ssl_verify=skip_ssl,
                request_snapshot=resolved_request,
            )
            result.attempt = attempt
            result.request_snapshot = raw_request_data

            if error or response is None:
                result.status = 'error'
                result.error_message = error or '请求失败且无响应'
                result.script_logs = list(result.script_logs or []) + attempt_logs
                if attempt < max_attempts:
                    time.sleep(retry_interval)
                    continue
                result.finished_at = timezone.now()
                result.save()
                return result

            # 4. 响应快照
            result.status_code = response.status_code
            result.response_time = response_time
            result.response_snapshot = self._snapshot_response(response)

            # 5. 断言:请求级 + 步骤级合并
            assertions = list(api_request.assertions or []) + list(step.assertions or [])
            assertion_results = run_assertions(response, assertions, response_time=response_time)
            result.assertions_results = assertion_results

            passed = all_passed(assertion_results)
            result.status = 'passed' if passed else 'failed'

            if not passed:
                # 失败重试
                if attempt < max_attempts:
                    result.script_logs = list(result.script_logs or []) + \
                        attempt_logs + [{'phase': 'retry', 'attempt': attempt + 1}]
                    time.sleep(retry_interval)
                    continue
                # 最后一次仍失败:仍执行提取与后置脚本(便于排查)
                result.error_message = self._summarize_assertion_errors(assertion_results)

            # 6. 变量提取
            try:
                extracted = self.extractor.extract(
                    response, api_request.extractors or [], self.context
                )
                result.extracted_vars = extracted
            except Exception as e:
                self.context.log('extractor_exception', error=str(e))

            # 7. 后置脚本
            if api_request.post_request_script:
                post_res = self.runtime.execute(
                    api_request.post_request_script,
                    self.context,
                    request_snapshot=resolved_request,
                    response=response,
                )
                attempt_logs.extend(post_res.get('logs') or [])
                if post_res.get('error'):
                    result.script_logs = list(result.script_logs or []) + \
                        [{'phase': 'post', 'error': post_res['error']}]

            result.script_logs = list(result.script_logs or []) + attempt_logs
            result.finished_at = timezone.now()
            result.save()

            # 8. 请求历史(可选)
            if self.persist_history:
                self._save_history(api_request, response, response_time,
                                    raw_request_data, assertion_results)

            return result

        # 兜底(理论不可达)
        result.finished_at = timezone.now()
        result.save()
        return result

    # ---------- 辅助:变量预解析(快照用) ----------

    def _preview_resolved_request(self, api_request: ApiRequest) -> Dict[str, Any]:
        resolver = VariableResolver()
        variables = self.context.merged()
        return {
            'method': api_request.method,
            'url': resolver.resolve(replace_placeholders(api_request.url or '', variables)),
            'headers': build_headers(api_request.headers, variables, resolver),
            'params': build_params(api_request.params, variables, resolver),
            'body_type': api_request.body.get('type') if isinstance(api_request.body, dict) else 'none',
            'body': resolve_value(
                api_request.body.get('data') if isinstance(api_request.body, dict) else None,
                variables, resolver
            ),
            'request_type': api_request.request_type,
        }

    # ---------- 辅助:响应快照 ----------

    def _snapshot_response(self, response) -> Dict[str, Any]:
        """响应快照(限制大小,避免撑爆数据库)"""
        try:
            headers = dict(response.headers or {})
        except Exception:
            headers = {}
        text = getattr(response, 'text', '') or ''
        # 截断超大响应(1MB)
        MAX_LEN = 1024 * 1024
        truncated = False
        if len(text) > MAX_LEN:
            text = text[:MAX_LEN]
            truncated = True
        snapshot = {
            'status_code': getattr(response, 'status_code', None),
            'headers': headers,
            'body': text,
            'truncated': truncated,
        }
        # 尝试带 json 字段
        if hasattr(response, 'json'):
            try:
                snapshot['json'] = response.json()
            except Exception:
                pass
        return snapshot

    # ---------- 辅助:历史记录 ----------

    def _save_history(self, api_request: ApiRequest, response, response_time: float,
                       request_data: Dict[str, Any], assertion_results: List[Dict[str, Any]]) -> None:
        try:
            content_type = ''
            try:
                content_type = response.headers.get('content-type', '') or ''
            except Exception:
                pass
            json_body = None
            if content_type and 'application/json' in content_type.lower():
                try:
                    json_body = response.json()
                except Exception:
                    json_body = None
            RequestHistory.objects.create(
                request=api_request,
                environment=self.environment,
                request_data=request_data,
                response_data={
                    'headers': dict(response.headers or {}),
                    'body': response.text,
                    'json': json_body,
                },
                status_code=response.status_code,
                response_time=response_time,
                assertions_results=assertion_results,
                executed_by=self.user,
            )
        except Exception as e:
            logger.warning("写入 RequestHistory 失败: %s", e)

    # ---------- 辅助:总结错误 ----------

    def _summarize_assertion_errors(self, assertion_results: List[Dict[str, Any]]) -> str:
        failures = [r for r in assertion_results if not r.get('passed', False)]
        if not failures:
            return ''
        first = failures[0]
        return first.get('error') or f"断言「{first.get('name')}」未通过"

    # ---------- 辅助:跳过 ----------

    def _mark_skipped(self, execution: TestExecution, step: TestSuiteRequest) -> None:
        api_request = step.request
        result = TestStepResult.objects.create(
            execution=execution,
            suite_request=step,
            request=api_request,
            request_name=api_request.name if api_request else '(已删除)',
            method=api_request.method if api_request else '',
            url=api_request.url if api_request else '',
            status='skipped',
            error_message='前置步骤触发 fail-fast,跳过执行',
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        self.all_step_results.append(result)
        self.legacy_results.append(self._to_legacy_result(step, result))

    def _to_legacy_result(self, step: TestSuiteRequest, result: TestStepResult) -> Dict[str, Any]:
        """生成兼容旧 results JSON 的字典"""
        return {
            'name': result.request_name,
            'method': result.method,
            'url': result.url,
            'status_code': result.status_code,
            'response_time': result.response_time,
            'passed': result.status == 'passed',
            'error': result.error_message,
            'assertions_results': result.assertions_results or [],
            'attempt': result.attempt,
            'extracted_vars': result.extracted_vars or {},
            'iteration': result.iteration,
        }

    # ---------- 收尾 ----------

    def _execution_for_save(self) -> Optional[TestExecution]:
        """保留用于向后兼容的查询入口,实际推荐直接传参"""
        return getattr(self, '_current_execution', None)

    def _finalize_success(self, execution: TestExecution) -> None:
        execution.status = 'COMPLETED' if self.failed_count == 0 else 'FAILED'
        self._finalize(execution)

    def _finalize(self, execution: TestExecution) -> None:
        execution.end_time = timezone.now()
        execution.passed_requests = self.passed_count
        execution.failed_requests = self.failed_count
        execution.results = {
            'total': self.total_count,
            'passed': self.passed_count,
            'failed': self.failed_count,
            'steps': self.legacy_results,
        }
        execution.save()


# ================ 全局变量收集 ================

def _collect_global_variables() -> Dict[str, Any]:
    """收集 scope=GLOBAL 且激活的 Environment 变量"""
    from .models import Environment
    try:
        envs = Environment.objects.filter(scope='GLOBAL', is_active=True)
        merged: Dict[str, Any] = {}
        for env in envs:
            merged.update(env.variables or {})
        return merged
    except Exception:
        return {}


# ================ 单接口试运行(不走套件) ================

def run_single_request(api_request: ApiRequest,
                        environment: Optional[Any] = None,
                        user: Optional[Any] = None,
                        persist_history: bool = True
                        ) -> Dict[str, Any]:
    """执行单接口(供 ApiRequestViewSet.execute 调用)

    返回兼容旧格式的字典,供序列化器消费:
        {
            'history': RequestHistory,
            'response_data': {...},
            'status_code': int,
            'response_time': float,
            'assertions_results': [...],
            'error': Optional[str],
        }
    """
    context = VariableContext()
    if environment:
        context.load_environment(environment.variables or {})
    context.load_globals(_collect_global_variables())

    # 前置脚本
    runtime = PythonScriptRuntime()
    if api_request.pre_request_script:
        runtime.execute(api_request.pre_request_script, context,
                         request_snapshot=None, response=None)

    response, response_time, error, resolved, raw_request = execute_request(
        api_request, context,
        timeout=api_request.timeout or 30,
        skip_ssl_verify=api_request.skip_ssl_verify or False,
    )

    if error or response is None:
        # 错误也要落历史
        if persist_history:
            history = RequestHistory.objects.create(
                request=api_request,
                environment=environment,
                request_data=raw_request,
                error_message=error or '请求失败且无响应',
                executed_by=user,
            )
            return {'history': history, 'error': error, 'status_code': None,
                     'response_time': None, 'assertions_results': [],
                     'response_data': None}
        return {'error': error, 'status_code': None, 'response_time': None,
                 'assertions_results': [], 'response_data': None}

    # 断言
    assertion_results = run_assertions(response, api_request.assertions or [],
                                        response_time=response_time)

    # 提取
    extractor = VariableExtractor()
    try:
        extractor.extract(response, api_request.extractors or [], context)
    except Exception as e:
        logger.warning("提取变量失败: %s", e)

    # 后置脚本
    if api_request.post_request_script:
        runtime.execute(api_request.post_request_script, context,
                         request_snapshot=resolved, response=response)

    # 历史
    history = None
    if persist_history:
        content_type = ''
        try:
            content_type = response.headers.get('content-type', '') or ''
        except Exception:
            pass
        json_body = None
        if content_type and 'application/json' in content_type.lower():
            try:
                json_body = response.json()
            except Exception:
                json_body = None
        history = RequestHistory.objects.create(
            request=api_request,
            environment=environment,
            request_data=raw_request,
            response_data={
                'headers': dict(response.headers or {}),
                'body': response.text,
                'json': json_body,
            },
            status_code=response.status_code,
            response_time=response_time,
            assertions_results=assertion_results,
            executed_by=user,
        )

    return {
        'history': history,
        'response_data': {
            'headers': dict(response.headers or {}),
            'body': response.text,
            'json': json_body,
        },
        'status_code': response.status_code,
        'response_time': response_time,
        'assertions_results': assertion_results,
        'error': None,
    }
