"""
接口自动化测试 - 报告生成器

支持两种输出格式:
  1. JUnit XML    Jenkins/GitLab CI 标准格式
  2. JSON         结构化数据,便于程序消费

设计原则:
  - 报告生成只读 TestExecution 与 TestStepResult,不发起额外查询
  - XML 用 xml.etree.ElementTree 构建,避免字符串拼接引入转义问题
  - 响应快照超过阈值时截断,避免报告膨胀
"""
import json
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET


# 响应快照在报告中保留的最大长度(字符数)
MAX_SNAPSHOT_IN_REPORT = 4096


def _truncate(text: Any, limit: int = MAX_SNAPSHOT_IN_REPORT) -> str:
    if text is None:
        return ''
    s = str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + f'\n...[truncated, {len(s)} chars total]'


def _safe_attr(value: Any) -> str:
    """安全转字符串,处理 None 与非字符串类型"""
    if value is None:
        return ''
    return str(value)


def build_junit_xml(execution) -> str:
    """从 TestExecution 生成 JUnit XML 字符串

    Args:
        execution: TestExecution 模型实例(需已 select_related test_suite)

    Returns:
        UTF-8 编码的 JUnit XML 字符串
    """
    suite = execution.test_suite
    suite_name = suite.name if suite else '(已删除套件)'
    classname = suite_name.replace(' ', '_')

    steps = list(execution.step_results.all().order_by('iteration', 'started_at'))

    tests_count = len(steps)
    failures = sum(1 for s in steps if s.status == 'failed')
    errors = sum(1 for s in steps if s.status == 'error')
    skipped = sum(1 for s in steps if s.status == 'skipped')

    # 时间统计(秒)
    total_time = 0.0
    for s in steps:
        if s.response_time:
            total_time += s.response_time / 1000.0

    # 构建根
    root = ET.Element('testsuites')
    suite_el = ET.SubElement(root, 'testsuite', {
        'name': suite_name,
        'tests': str(tests_count),
        'failures': str(failures),
        'errors': str(errors),
        'skipped': str(skipped),
        'time': f'{total_time:.3f}',
        'timestamp': execution.start_time.isoformat() if execution.start_time else '',
    })

    # 系统级元数据(便于排查)
    ET.SubElement(suite_el, 'properties')
    props = suite_el.find('properties')
    ET.SubElement(props, 'property', {
        'name': 'execution_id', 'value': str(execution.id),
    })
    ET.SubElement(props, 'property', {
        'name': 'trigger_source', 'value': execution.trigger_source or 'manual',
    })
    if execution.stop_reason:
        ET.SubElement(props, 'property', {
            'name': 'stop_reason', 'value': _truncate(execution.stop_reason, 500),
        })

    # 步骤
    for step in steps:
        case_time = (step.response_time or 0) / 1000.0
        case_name = step.request_name or '(未命名步骤)'
        if step.iteration:
            case_name = f'{case_name} [iter={step.iteration}]'

        case_el = ET.SubElement(suite_el, 'testcase', {
            'classname': classname,
            'name': case_name,
            'time': f'{case_time:.3f}',
        })

        if step.status == 'passed':
            continue

        if step.status == 'failed':
            # 断言失败详情
            fail_msg = step.error_message or '断言未通过'
            fail_type = 'AssertionFailure'
            detail_lines: List[str] = [fail_msg]
            for r in (step.assertions_results or []):
                if not r.get('passed', False):
                    detail_lines.append(
                        f"- {r.get('name', '')}: source={r.get('source')} "
                        f"operator={r.get('operator')} expected={r.get('expected')!r} "
                        f"actual={r.get('actual')!r}"
                    )
            ET.SubElement(case_el, 'failure', {
                'message': _truncate(fail_msg, 1000),
                'type': fail_type,
            }).text = _truncate('\n'.join(detail_lines))

        elif step.status == 'error':
            # 异常
            ET.SubElement(case_el, 'error', {
                'message': _truncate(step.error_message or '执行异常', 1000),
                'type': 'ExecutionError',
            }).text = _truncate(step.error_message)

        elif step.status == 'skipped':
            ET.SubElement(case_el, 'skipped', {
                'message': _truncate(step.error_message or '跳过', 500),
            })

    # 收尾
    ET.SubElement(suite_el, 'system-out').text = _truncate(
        json.dumps({
            'passed': execution.passed_requests,
            'failed': execution.failed_requests,
            'total': execution.total_requests,
        }, ensure_ascii=False),
        2000,
    )

    # 序列化(UTF-8 + XML 声明)
    xml_bytes = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return xml_bytes.decode('utf-8')


def build_json_report(execution, include_snapshots: bool = True) -> Dict[str, Any]:
    """从 TestExecution 生成结构化 JSON 报告

    Args:
        execution: TestExecution 模型实例
        include_snapshots: 是否包含请求/响应快照(可能较大,CI 输出建议 False)

    Returns:
        dict,可直接 json.dumps
    """
    suite = execution.test_suite

    steps_data: List[Dict[str, Any]] = []
    steps = list(execution.step_results.all().order_by('iteration', 'started_at'))

    for step in steps:
        item: Dict[str, Any] = {
            'iteration': step.iteration,
            'name': step.request_name,
            'method': step.method,
            'url': step.url,
            'status': step.status,
            'status_code': step.status_code,
            'response_time_ms': step.response_time,
            'attempt': step.attempt,
            'error': step.error_message,
            'assertions': [
                {
                    'name': r.get('name'),
                    'passed': r.get('passed'),
                    'source': r.get('source'),
                    'operator': r.get('operator'),
                    'expected': r.get('expected'),
                    'actual': r.get('actual'),
                    'error': r.get('error'),
                }
                for r in (step.assertions_results or [])
            ],
            'extracted_vars': step.extracted_vars or {},
        }
        if include_snapshots:
            item['request_snapshot'] = step.request_snapshot
            item['response_snapshot'] = step.response_snapshot
            item['script_logs'] = step.script_logs
        steps_data.append(item)

    return {
        'execution': {
            'id': execution.id,
            'status': execution.status,
            'trigger_source': execution.trigger_source,
            'started_at': execution.start_time.isoformat() if execution.start_time else None,
            'ended_at': execution.end_time.isoformat() if execution.end_time else None,
            'duration_seconds': _duration_seconds(execution),
            'stop_reason': execution.stop_reason,
        },
        'suite': {
            'id': suite.id if suite else None,
            'name': suite.name if suite else '(已删除)',
        },
        'summary': {
            'total': execution.total_requests,
            'passed': execution.passed_requests,
            'failed': execution.failed_requests,
            'skipped': sum(1 for s in steps if s.status == 'skipped'),
            'errored': sum(1 for s in steps if s.status == 'error'),
            'pass_rate': _pass_rate(execution),
        },
        'steps': steps_data,
    }


def _duration_seconds(execution) -> Optional[float]:
    if not execution.start_time or not execution.end_time:
        return None
    return (execution.end_time - execution.start_time).total_seconds()


def _pass_rate(execution) -> Optional[float]:
    total = execution.total_requests or 0
    if total == 0:
        return None
    return round((execution.passed_requests or 0) * 100.0 / total, 2)


# ---------- 工具:写入文件 ----------

def write_report(path: str, content: str) -> None:
    """把报告写入文件,父目录不存在则创建"""
    import os
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def build_report(execution, fmt: str = 'json',
                  include_snapshots: bool = True) -> str:
    """根据格式生成报告字符串

    Args:
        execution: TestExecution 实例
        fmt: 'json' / 'junit' / 'xml'(junit 的别名)
        include_snapshots: 仅对 json 有效

    Returns:
        报告字符串
    """
    fmt = (fmt or 'json').lower()
    if fmt in ('junit', 'xml'):
        return build_junit_xml(execution)
    if fmt == 'json':
        return json.dumps(build_json_report(execution, include_snapshots=include_snapshots),
                          ensure_ascii=False, indent=2, default=str)
    raise ValueError(f"未知报告格式: {fmt},支持 json / junit")
