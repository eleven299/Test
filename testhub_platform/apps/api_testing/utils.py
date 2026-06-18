import json
import time
from django.utils import timezone
from .models import RequestHistory
from .variable_resolver import VariableResolver


def execute_assertions(response, assertions):
    """执行断言验证(向后兼容入口,内部委托给 assertions.run_assertions)

    旧调用方在 assertion 字典里塞入 actual_time 表示响应时间,
    本函数会把它取出传给新的统一接口。
    """
    from .assertions import run_assertions

    if not assertions:
        return []

    # 从旧格式断言里提取响应时间(response_time 类型断言会用)
    response_time = None
    for assertion in assertions:
        if isinstance(assertion, dict) and assertion.get('type') == 'response_time':
            response_time = assertion.get('actual_time')
            break

    return run_assertions(response, assertions, response_time=response_time)


def execute_test_suite(test_suite, environment, executed_by):
    """执行测试套件(薄包装,委托给 engine.TestExecutionEngine)

    保留旧返回格式以兼容定时任务等调用方:
        {'success': bool, 'execution_id': int, 'passed_count': int,
         'failed_count': int, 'total_count': int, 'results': list}
    """
    from .engine import TestExecutionEngine

    try:
        engine = TestExecutionEngine(
            test_suite=test_suite,
            environment=environment,
            user=executed_by,
            trigger_source='schedule',
            persist_history=True,
        )
        execution = engine.run()
        return {
            'success': execution.failed_requests == 0,
            'execution_id': execution.id,
            'passed_count': execution.passed_requests,
            'failed_count': execution.failed_requests,
            'total_count': execution.total_requests,
            'results': (execution.results or {}).get('steps', []) if isinstance(execution.results, dict) else [],
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def execute_api_request(api_request, environment, executed_by):
    """执行单个 API 请求(薄包装,委托给 engine.run_single_request)

    保留旧返回格式以兼容定时任务等调用方。
    """
    from .engine import run_single_request

    try:
        result = run_single_request(
            api_request=api_request,
            environment=environment,
            user=executed_by,
            persist_history=True,
        )
        if result.get('error'):
            return {'success': False, 'error': result['error']}
        return {
            'success': True,
            'history_id': result['history'].id if result.get('history') else None,
            'status_code': result.get('status_code'),
            'response_time': result.get('response_time'),
            'assertions_results': result.get('assertions_results') or [],
            'response_data': result.get('response_data'),
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _replace_variables(text, variables):
    """替换文本中的变量"""
    if not isinstance(text, str):
        return text
    
    result = text
    for key, value in (variables or {}).items():
        if isinstance(value, dict):
            replacement = str(value.get('currentValue', '') or value.get('initialValue', ''))
        else:
            replacement = str(value) if value is not None else ''
        result = result.replace(f'{{{{{key}}}}}', replacement)
    return result

def _replace_variables_in_dict(data, variables):
    """递归替换字典中的变量"""
    if isinstance(data, dict):
        return {k: _replace_variables_in_dict(v, variables) for k, v in data.items()}
    elif isinstance(data, list):
        return [_replace_variables_in_dict(item, variables) for item in data]
    elif isinstance(data, str):
        return _replace_variables(data, variables)
    else:
        return data

def _resolve_variables_in_dict(data, resolver):
    """递归解析字典中的动态函数占位符"""
    if isinstance(data, dict):
        return {k: _resolve_variables_in_dict(v, resolver) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_variables_in_dict(item, resolver) for item in data]
    elif isinstance(data, str):
        return resolver.resolve(data)
    else:
        return data
