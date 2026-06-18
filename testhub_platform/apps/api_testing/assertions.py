"""
接口自动化测试 - 断言系统(P0 重构)

引入 source + operator + expected 三段式断言结构,
扩展操作符种类,并兼容旧版 type 字段格式。

新断言 JSON 结构:
    {
        "name": "校验返回 code 字段",
        "source": "json_body",          status_code / response_time / json_body / header / raw_body
        "expression": "$.code",         JSONPath / header 名(根据 source 解释)
        "operator": "equals",           见 Operator 枚举
        "expected": 0,
        "message": "code 应为 0"
    }

旧断言(type 字段)兼容映射:
    status_code    -> source=status_code, operator=equals
    response_time  -> source=response_time, operator=less_equal
    contains       -> source=raw_body, operator=contains
    json_path      -> source=json_body, operator=equals, expression=<json_path>
    header         -> source=header, operator=equals, expression=<header_name>
    equals         -> source=raw_body, operator=equals
"""
import json
import re
from typing import Any, Dict, List, Optional


# ---------- 操作符定义 ----------

class Operator:
    EQUALS = 'equals'
    NOT_EQUALS = 'not_equals'
    CONTAINS = 'contains'
    NOT_CONTAINS = 'not_contains'
    GREATER_THAN = 'greater_than'
    LESS_THAN = 'less_than'
    GREATER_EQUAL = 'greater_equal'
    LESS_EQUAL = 'less_equal'
    IN_ARRAY = 'in_array'              # actual in expected(list)
    NOT_IN_ARRAY = 'not_in_array'
    REGEX = 'regex'
    LENGTH_EQUALS = 'length_eq'
    EXISTS = 'exists'                  # actual 不为 None
    NOT_EXISTS = 'not_exists'
    TYPE_IS = 'type_is'                # 类型断言


# 旧 type -> 新 (source, operator, expression_field) 映射
_LEGACY_TYPE_MAP = {
    'status_code':   {'source': 'status_code', 'operator': Operator.EQUALS},
    'response_time': {'source': 'response_time', 'operator': Operator.LESS_EQUAL},
    'contains':      {'source': 'raw_body', 'operator': Operator.CONTAINS},
    'json_path':     {'source': 'json_body', 'operator': Operator.EQUALS,
                       '_expression_key': 'json_path'},
    'header':        {'source': 'header', 'operator': Operator.EQUALS,
                       '_expression_key': 'header_name'},
    'equals':        {'source': 'raw_body', 'operator': Operator.EQUALS},
}


def _normalize_assertion(assertion: Dict[str, Any]) -> Dict[str, Any]:
    """旧格式自动转新格式;新格式直接返回"""
    if not isinstance(assertion, dict):
        return {'source': 'raw_body', 'operator': Operator.EQUALS,
                 'expected': None, 'name': '无效断言'}

    # 已经是新格式
    if 'operator' in assertion and 'source' in assertion:
        return assertion

    # 旧格式:基于 type 字段
    legacy_type = assertion.get('type')
    if legacy_type and legacy_type in _LEGACY_TYPE_MAP:
        mapping = dict(_LEGACY_TYPE_MAP[legacy_type])
        expr_key = mapping.pop('_expression_key', None)

        # expected 来源:优先 expected,其次 expected_value,最后 value
        # 注意:不能用 `or` 链,否则 expected=0 这种 falsy 值会被吞掉
        expected = assertion.get('expected')
        if expected is None:
            expected = assertion.get('expected_value')
        if expected is None:
            expected = assertion.get('value')

        normalized = {
            'name': assertion.get('name', '未命名断言'),
            'source': mapping['source'],
            'operator': mapping['operator'],
            'expected': expected,
            'message': assertion.get('message', ''),
        }
        # expression 来源
        if expr_key and assertion.get(expr_key):
            normalized['expression'] = assertion.get(expr_key)
        elif legacy_type == 'json_path':
            normalized['expression'] = assertion.get('json_path', '')
        elif legacy_type == 'header':
            normalized['expression'] = assertion.get('header_name', '')
        return normalized

    # 兜底:把 type 当作 source 处理
    return {
        'name': assertion.get('name', '未命名断言'),
        'source': legacy_type or 'raw_body',
        'operator': Operator.EQUALS,
        'expected': assertion.get('expected'),
        'message': assertion.get('message', ''),
    }


# ---------- 实际值解析 ----------

def _response_to_dict(response) -> Dict[str, Any]:
    """统一响应对象结构(兼容 requests.Response 与 WebSocketResponse)"""
    headers = getattr(response, 'headers', {}) or {}
    text = getattr(response, 'text', '') or ''
    status_code = getattr(response, 'status_code', None)

    json_body = None
    if hasattr(response, 'json'):
        try:
            json_body = response.json()
        except Exception:
            json_body = None
    if json_body is None and text:
        try:
            content_type = ''
            if hasattr(headers, 'get'):
                content_type = headers.get('content-type', '') or ''
            if 'application/json' in content_type.lower():
                json_body = json.loads(text)
        except Exception:
            json_body = None

    return {
        'headers': headers,
        'text': text,
        'status_code': status_code,
        'json': json_body,
    }


def _resolve_actual(resp_info: Dict[str, Any], source: str,
                     expression: Optional[str]) -> Any:
    """根据 source 解析实际值"""
    if source == 'status_code':
        return resp_info.get('status_code')
    if source == 'response_time':
        # 由调用方写入 resp_info['__response_time__']
        return resp_info.get('__response_time__')
    if source == 'raw_body':
        return resp_info.get('text', '')
    if source == 'header':
        if not expression:
            raise ValueError("header 名不能为空")
        headers = resp_info.get('headers') or {}
        if hasattr(headers, 'get'):
            value = headers.get(expression)
            if value is not None:
                return value
        lower = expression.lower()
        for k, v in dict(headers).items():
            if k.lower() == lower:
                return v
        return None
    if source == 'json_body':
        if not expression:
            raise ValueError("JSONPath 表达式不能为空")
        body = resp_info.get('json')
        if body is None:
            raise ValueError("响应不是 JSON 格式")
        try:
            from jsonpath_ng import parse as jp_parse
        except ImportError as e:
            raise ValueError(f"缺少依赖 jsonpath_ng: {e}")
        try:
            matches = jp_parse(expression).find(body)
        except Exception as e:
            raise ValueError(f"JSONPath 解析失败: {e}")
        if not matches:
            return None  # 无匹配,允许配合 exists/not_exists/equals 判断
        return matches[0].value
    raise ValueError(f"未知 source: {source!r}")


# ---------- 操作符执行 ----------

def _apply_operator(op: str, actual: Any, expected: Any) -> bool:
    """根据操作符比较 actual 与 expected"""
    if op == Operator.EXISTS:
        return actual is not None
    if op == Operator.NOT_EXISTS:
        return actual is None
    if op == Operator.EQUALS:
        return _safe_equal(actual, expected)
    if op == Operator.NOT_EQUALS:
        return not _safe_equal(actual, expected)
    if op == Operator.CONTAINS:
        if actual is None:
            return False
        if isinstance(actual, (list, tuple, dict, set)):
            return expected in actual
        return str(expected) in str(actual)
    if op == Operator.NOT_CONTAINS:
        if actual is None:
            return True
        if isinstance(actual, (list, tuple, dict, set)):
            return expected not in actual
        return str(expected) not in str(actual)
    if op == Operator.GREATER_THAN:
        return _numeric(actual) > _numeric(expected)
    if op == Operator.LESS_THAN:
        return _numeric(actual) < _numeric(expected)
    if op == Operator.GREATER_EQUAL:
        return _numeric(actual) >= _numeric(expected)
    if op == Operator.LESS_EQUAL:
        return _numeric(actual) <= _numeric(expected)
    if op == Operator.IN_ARRAY:
        if not isinstance(expected, (list, tuple, set)):
            return _safe_equal(actual, expected)
        return _safe_in_array(actual, expected)
    if op == Operator.NOT_IN_ARRAY:
        if not isinstance(expected, (list, tuple, set)):
            return not _safe_equal(actual, expected)
        return not _safe_in_array(actual, expected)
    if op == Operator.REGEX:
        if actual is None:
            return False
        return re.search(str(expected), str(actual)) is not None
    if op == Operator.LENGTH_EQUALS:
        if actual is None or not hasattr(actual, '__len__'):
            return False
        return len(actual) == _numeric(expected)
    if op == Operator.TYPE_IS:
        type_map = {
            'int': int, 'float': float, 'str': str, 'bool': bool,
            'list': list, 'dict': dict, 'None': type(None),
        }
        expected_type = type_map.get(str(expected))
        if expected_type is None:
            return False
        return isinstance(actual, expected_type)
    raise ValueError(f"未知操作符: {op!r}")


def _safe_equal(actual: Any, expected: Any) -> bool:
    """宽松相等:数字/字符串/布尔做容错比较"""
    if actual is None and expected is None:
        return True
    if actual is None or expected is None:
        return False
    # 数字比较(容许 int vs str)
    try:
        if isinstance(actual, (int, float)) or isinstance(expected, (int, float)):
            return float(actual) == float(expected)
    except (ValueError, TypeError):
        pass
    return str(actual) == str(expected)


def _safe_in_array(actual: Any, expected_list) -> bool:
    for item in expected_list:
        if _safe_equal(actual, item):
            return True
    return False


def _numeric(value: Any) -> float:
    """转数字,失败抛 ValueError"""
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"无法比较非数字值: {value!r}")


# ---------- 统一入口 ----------

def run_assertions(response, assertions: List[Dict[str, Any]],
                   response_time: Optional[float] = None) -> List[Dict[str, Any]]:
    """执行批量断言

    Args:
        response: requests.Response 或 duck-type 兼容对象
        assertions: 断言规则列表(支持新 source+operator 格式与旧 type 格式)
        response_time: 响应时间(毫秒),供 response_time 类断言使用

    Returns:
        [{'name', 'passed', 'expected', 'actual', 'error', 'source', 'operator'}]
    """
    if not assertions:
        return []

    resp_info = _response_to_dict(response)
    if response_time is not None:
        resp_info['__response_time__'] = response_time

    results: List[Dict[str, Any]] = []
    for assertion in assertions:
        normalized = _normalize_assertion(assertion)
        source = normalized.get('source', 'raw_body')
        operator = normalized.get('operator', Operator.EQUALS)
        expression = normalized.get('expression')
        expected = normalized.get('expected')
        name = normalized.get('name') or f"{source}.{operator}"

        result = {
            'name': name,
            'type': assertion.get('type') if isinstance(assertion, dict) else None,
            'source': source,
            'operator': operator,
            'expected': expected,
            'actual': None,
            'passed': False,
            'error': None,
        }

        try:
            actual = _resolve_actual(resp_info, source, expression)
            result['actual'] = actual
            passed = _apply_operator(operator, actual, expected)
            result['passed'] = passed
            if not passed:
                msg = normalized.get('message') or \
                    f"断言失败: {source}({expression}) {operator} {expected!r}, 实际 {actual!r}"
                result['error'] = msg
        except Exception as e:
            result['error'] = str(e)
            result['passed'] = False

        results.append(result)

    return results


def all_passed(assertion_results: List[Dict[str, Any]]) -> bool:
    """判断断言结果列表是否全部通过"""
    return all(r.get('passed', False) for r in assertion_results)
