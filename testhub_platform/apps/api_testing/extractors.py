"""
接口自动化测试 - 变量提取器

从响应中按规则提取值,写入 VariableContext 供后续请求使用。

提取规则 JSON 结构:
    {
        "name": "token",                 必填,变量名
        "source": "json_body",           必填,取值来源
        "expression": "$.data.token",    必填(JSONPath / header name / 正则等)
        "target_scope": "extracted",     可选,默认 extracted
        "default": "",                   可选,提取失败时的兜底值
        "group": 1                       可选,仅 source=regex 时生效
    }

source 取值:
    json_body    - JSONPath 表达式,作用于响应 JSON
    header       - 响应头字段名(大小写不敏感)
    status_code  - HTTP 状态码(忽略 expression)
    regex        - 正则匹配响应文本,取第 N 个捕获组
    raw_body     - 原始响应文本(忽略 expression)
    xml_body     - XPath 表达式,作用于响应 XML
"""
import json
import re
from typing import Any, Dict, List


class ExtractionError(Exception):
    """提取失败异常(非致命)"""


def _response_to_dict(response) -> Dict[str, Any]:
    """把响应对象转为统一结构(兼容 requests.Response 与 WebSocketResponse)"""
    headers = getattr(response, 'headers', {}) or {}
    text = getattr(response, 'text', '') or ''
    status_code = getattr(response, 'status_code', None)

    # 尝试解析 JSON
    json_body = None
    if hasattr(response, 'json'):
        try:
            json_body = response.json()
        except Exception:
            json_body = None
    if json_body is None:
        content_type = ''
        try:
            content_type = headers.get('content-type', '') if hasattr(headers, 'get') else ''
        except Exception:
            content_type = ''
        if 'application/json' in (content_type or '').lower() and text:
            try:
                json_body = json.loads(text)
            except Exception:
                json_body = None

    return {
        'headers': headers,
        'text': text,
        'status_code': status_code,
        'json': json_body,
    }


class VariableExtractor:
    """从响应中按规则提取变量"""

    def extract(self, response, extractors: List[Dict[str, Any]], context) -> Dict[str, Any]:
        """执行批量提取,返回成功提取的变量字典

        Args:
            response: requests.Response 或 duck-type 兼容对象
            extractors: 提取规则列表
            context: VariableContext 实例

        Returns:
            本次成功提取的变量 {name: value}(不含 default 兜底)
        """
        extracted: Dict[str, Any] = {}
        if not extractors:
            return extracted

        resp_info = _response_to_dict(response)

        for idx, rule in enumerate(extractors):
            name = rule.get('name') or f'_unnamed_{idx}'
            scope = rule.get('target_scope', 'extracted')
            try:
                value = self._extract_one(resp_info, rule)
                context.set(name, value, scope=scope)
                extracted[name] = value
            except Exception as e:
                # 提取失败不阻塞,记录日志,使用 default(若有)
                context.log('extract_failed', name=name, error=str(e),
                             rule=rule, source=rule.get('source'))
                if 'default' in rule:
                    context.set(name, rule['default'], scope=scope)
                    extracted[name] = rule['default']

        return extracted

    def _extract_one(self, resp_info: Dict[str, Any], rule: Dict[str, Any]) -> Any:
        source = (rule.get('source') or '').lower()
        expression = rule.get('expression')

        if source == 'json_body':
            return self._from_json(resp_info, expression)
        if source == 'header':
            return self._from_header(resp_info, expression)
        if source == 'status_code':
            return resp_info.get('status_code')
        if source == 'regex':
            return self._from_regex(resp_info, expression, rule.get('group', 0))
        if source == 'raw_body':
            return resp_info.get('text', '')
        if source == 'xml_body':
            return self._from_xml(resp_info, expression)
        raise ExtractionError(f"未知 source: {source!r}")

    # ----- 各 source 实现 -----

    def _from_json(self, resp_info: Dict[str, Any], json_path: str) -> Any:
        if not json_path:
            raise ExtractionError("JSONPath 表达式不能为空")
        body = resp_info.get('json')
        if body is None:
            raise ExtractionError("响应不是 JSON 格式,无法用 json_body 提取")
        try:
            from jsonpath_ng import parse as jp_parse
        except ImportError as e:
            raise ExtractionError(f"缺少依赖 jsonpath_ng: {e}")
        try:
            matches = jp_parse(json_path).find(body)
        except Exception as e:
            raise ExtractionError(f"JSONPath 解析失败: {e}")
        if not matches:
            raise ExtractionError(f"JSONPath 无匹配: {json_path}")
        return matches[0].value

    def _from_header(self, resp_info: Dict[str, Any], header_name: str) -> Any:
        if not header_name:
            raise ExtractionError("header 名不能为空")
        headers = resp_info.get('headers') or {}
        # 大小写不敏感查找
        if hasattr(headers, 'get'):
            # requests.Headers 支持大小写不敏感 get
            value = headers.get(header_name)
            if value is not None:
                return value
            # 退化到手写大小写不敏感查找
            lower = header_name.lower()
            for k, v in dict(headers).items():
                if k.lower() == lower:
                    return v
        return None  # 明确返回 None,由调用方决定是否给 default

    def _from_regex(self, resp_info: Dict[str, Any], pattern: str, group: int = 0) -> Any:
        if not pattern:
            raise ExtractionError("正则表达式不能为空")
        text = resp_info.get('text', '')
        m = re.search(pattern, text)
        if not m:
            raise ExtractionError(f"正则无匹配: {pattern}")
        try:
            return m.group(group)
        except IndexError:
            raise ExtractionError(f"正则捕获组 {group} 不存在,模式仅含 {m.re.groups} 个组")

    def _from_xml(self, resp_info: Dict[str, Any], xpath: str) -> Any:
        if not xpath:
            raise ExtractionError("XPath 表达式不能为空")
        try:
            from lxml import etree
        except ImportError as e:
            raise ExtractionError(f"缺少依赖 lxml: {e}")
        text = resp_info.get('text', '')
        if not text:
            raise ExtractionError("响应体为空")
        try:
            tree = etree.fromstring(text.encode('utf-8') if isinstance(text, str) else text)
        except Exception as e:
            raise ExtractionError(f"XML 解析失败: {e}")
        results = tree.xpath(xpath)
        if not results:
            raise ExtractionError(f"XPath 无匹配: {xpath}")
        first = results[0]
        # lxml 节点对象转为字符串
        if hasattr(first, 'text'):
            return first.text
        return first
