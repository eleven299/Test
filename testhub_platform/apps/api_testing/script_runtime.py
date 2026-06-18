"""
接口自动化测试 - 前后置脚本运行时(Python)

提供受限沙箱执行用户编写的 Python 脚本。

安全策略:
  1. AST 预检:拒绝 import / open / eval / exec / __import__ / os.system 等危险节点
  2. __builtins__ 白名单:仅暴露安全内建函数
  3. 显式注入常用模块(json/re/time/datetime/hashlib/base64/math/random)

注入对象:
  ctx       ScriptContext 实例
  ctx.vars  可读可写的变量字典(写入等价于 context.set(name, value, 'request'))
  ctx.request   请求快照(pre 阶段可用,只读)
  ctx.response  响应对象(post 阶段可用,只读)
  ctx.log(msg)  记录日志

脚本示例(后置 - 提取 token 并算签名):
    data = ctx.response.json()
    ctx.vars.token = data['data']['access_token']
    import hashlib, time as _t  # ❌ 会被 AST 预检拒绝,直接用注入的 hashlib/time
    ts = str(int(time.time()))
    ctx.vars.sign = hashlib.md5(f"{ctx.vars.token}{ts}".encode()).hexdigest()
    ctx.vars.timestamp = ts
"""
import ast
import json
import re
import time
import math
import random
import hashlib
import base64
import datetime
import logging
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


# ---------- 沙箱安全策略 ----------

# 允许的 builtins(白名单)
SAFE_BUILTINS: Dict[str, Any] = {
    'len': len, 'str': str, 'int': int, 'float': float,
    'bool': bool, 'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
    'range': range, 'enumerate': enumerate, 'zip': zip,
    'map': map, 'filter': filter, 'sorted': sorted, 'reversed': reversed,
    'min': min, 'max': max, 'sum': sum, 'abs': abs,
    'round': round, 'all': all, 'any': any,
    'isinstance': isinstance, 'type': type,
    'True': True, 'False': False, 'None': None,
    'print': lambda *args, **kw: None,    # 静默
}

# 危险名称(属性访问 / 函数名)
# 注意:'vars' 不在此列表 - 沙箱 __builtins__ 未注入 vars(),运行时本就 NameError;
# 把 'vars' 列入会误伤 ctx.vars 这种合法属性访问。
DANGEROUS_NAMES = {
    '__import__', 'eval', 'exec', 'compile', 'open', 'globals', 'locals',
    'getattr', 'setattr', 'delattr', 'input',
    'breakpoint', 'exit', 'quit', 'memoryview', 'bytearray',
}

# 禁止的模块(顶层 import)
FORBIDDEN_MODULES = {
    'os', 'sys', 'subprocess', 'shutil', 'pathlib',
    'socket', 'http', 'urllib', 'requests', 'asyncio',
    'multiprocessing', 'threading', 'ctypes', 'pickle',
    'marshal', 'importlib', 'builtins', 'gc',
}

# 显式注入的安全模块
SAFE_MODULES: Dict[str, Any] = {
    'json': json,
    're': re,
    'time': time,
    'math': math,
    'random': random,
    'hashlib': hashlib,
    'base64': base64,
    'datetime': datetime,
}


class ScriptSecurityError(Exception):
    """脚本安全检查失败"""


class ScriptValidator(ast.NodeVisitor):
    """AST 预检器,拒绝危险节点"""

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split('.')[0]
            if top in FORBIDDEN_MODULES:
                raise ScriptSecurityError(f"禁止导入模块: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            top = node.module.split('.')[0]
            if top in FORBIDDEN_MODULES:
                raise ScriptSecurityError(f"禁止从模块导入: {node.module}")
        for alias in node.names:
            if alias.name == '*':
                raise ScriptSecurityError("禁止 from X import *")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        attr = node.attr
        # 禁止访问以 __ 开头的属性(逃逸常用手段)
        if attr.startswith('__'):
            raise ScriptSecurityError(f"禁止访问下划线属性: {attr}")
        # 禁止访问已知危险属性名
        if attr in DANGEROUS_NAMES:
            raise ScriptSecurityError(f"禁止访问属性: {attr}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in DANGEROUS_NAMES:
            raise ScriptSecurityError(f"禁止使用名称: {node.id}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # 拦截 __import__ / eval / exec 形式的调用
        func = node.func
        if isinstance(func, ast.Name) and func.id in DANGEROUS_NAMES:
            raise ScriptSecurityError(f"禁止调用: {func.id}")
        self.generic_visit(node)


def validate_script(source: str) -> None:
    """对脚本做 AST 安全预检,失败抛 ScriptSecurityError"""
    if not source or not source.strip():
        return
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ScriptSecurityError(f"脚本语法错误: {e}")
    ScriptValidator().visit(tree)


# ---------- 暴露给脚本的对象 ----------

class ScriptVars:
    """变量代理:读写都落到 VariableContext 的 request 作用域"""

    def __init__(self, context):
        self._context = context

    def __getattr__(self, name: str) -> Any:
        if name.startswith('_'):
            raise AttributeError(name)
        return self._context.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            self._context.set(name, value, scope='request')

    def __contains__(self, name: str) -> bool:
        return self._context.has(name)

    def __repr__(self) -> str:
        return f"<ScriptVars {self._context.merged()!r}>"


class ScriptContext:
    """脚本运行时暴露的上下文对象"""

    def __init__(self, context, request_snapshot: Dict[str, Any] = None,
                 response=None):
        self._context = context
        self.vars = ScriptVars(context)
        # request / response 设为只读属性(通过 property 拦截赋值)
        self._request = request_snapshot or {}
        self._response = response
        self._logs: List[str] = []

    @property
    def request(self) -> Dict[str, Any]:
        return self._request

    @property
    def response(self):
        return self._response

    def log(self, message: Any) -> None:
        """记录脚本日志"""
        self._logs.append(str(message))

    @property
    def logs(self) -> List[str]:
        return list(self._logs)


# ---------- 运行时 ----------

class PythonScriptRuntime:
    """Python 脚本运行时"""

    def execute(self, script: str, context, request_snapshot: Dict[str, Any] = None,
                response=None) -> Dict[str, Any]:
        """执行脚本

        Args:
            script: 脚本源码
            context: VariableContext
            request_snapshot: 请求快照(pre 阶段可用)
            response: 响应对象(post 阶段可用,pre 时为 None)

        Returns:
            {'logs': [...], 'error': Optional[str]}
        """
        result = {'logs': [], 'error': None}
        if not script or not script.strip():
            return result

        # 1. AST 预检
        try:
            validate_script(script)
        except ScriptSecurityError as e:
            result['error'] = f"[安全拦截] {e}"
            context.log('script_blocked', error=str(e))
            logger.warning("脚本被安全策略拦截: %s", e)
            return result

        # 2. 构造沙箱环境
        script_ctx = ScriptContext(context, request_snapshot=request_snapshot,
                                    response=response)
        sandbox_globals: Dict[str, Any] = {
            '__builtins__': SAFE_BUILTINS,
            'ctx': script_ctx,
            **SAFE_MODULES,
        }

        # 3. 执行
        try:
            exec(compile(script, '<api_testing_script>', 'exec'),  # noqa: S102
                 sandbox_globals)
        except Exception as e:
            result['error'] = f"{type(e).__name__}: {e}"
            context.log('script_error', error=result['error'])

        result['logs'] = script_ctx.logs
        return result
