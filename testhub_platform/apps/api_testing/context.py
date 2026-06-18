"""
接口自动化测试 - 变量上下文

实现 5 级变量作用域,优先级从低到高:
  L1 global      全局变量(整个进程内)
  L2 environment 环境变量(Environment 表)
  L3 extracted   提取变量(套件执行内跨请求传递,默认作用域)
  L4 iteration   迭代变量(DDT 单次迭代内)
  L5 request     请求级临时变量(前置脚本设置,仅当前请求可见)

引用语法:
  {{var_name}}           变量替换
  ${func(args)}          动态函数(由 core.variable_resolver 处理)

线程安全说明:
  - 单次套件执行内,引擎是同步串行的,无需加锁
  - 全局层(L1)如果跨套件共享,调用方需自行加锁
"""
from typing import Any, Dict, List, Optional


VALID_SCOPES = ('global', 'environment', 'extracted', 'iteration', 'request')


class VariableContext:
    """接口测试执行期变量上下文"""

    def __init__(self):
        # 按优先级从低到高排列,后者覆盖前者
        self._layers: Dict[str, Dict[str, Any]] = {
            'global': {},
            'environment': {},
            'extracted': {},
            'iteration': {},       # 当前迭代(由 push_iteration/pop_iteration 维护栈顶)
            'request': {},
        }
        # 迭代栈:DDT 时多级嵌套(理论上一套件只有一层,这里支持嵌套以防未来扩展)
        self._iteration_stack: List[Dict[str, Any]] = []
        # 日志收集(提取失败、脚本日志等)
        self.logs: List[Dict[str, Any]] = []

    # ---------- 写入 ----------

    def set(self, name: str, value: Any, scope: str = 'extracted') -> None:
        """向指定作用域写入变量"""
        if scope not in VALID_SCOPES:
            raise ValueError(f"非法 scope: {scope}, 必须为 {VALID_SCOPES}")
        if name is None or name == '':
            raise ValueError("变量名不能为空")
        self._layers[scope][name] = value

    def update(self, mapping: Dict[str, Any], scope: str = 'extracted') -> None:
        """批量写入"""
        if scope not in VALID_SCOPES:
            raise ValueError(f"非法 scope: {scope}")
        self._layers[scope].update(mapping or {})

    # ---------- 读取 ----------

    def get(self, name: str, default: Any = None) -> Any:
        """按优先级从高到低查找变量"""
        for scope in reversed(VALID_SCOPES):
            if name in self._layers[scope]:
                return self._layers[scope][name]
        return default

    def has(self, name: str) -> bool:
        for scope in reversed(VALID_SCOPES):
            if name in self._layers[scope]:
                return True
        return False

    def merged(self) -> Dict[str, Any]:
        """返回合并后的变量字典(低优先级被高优先级覆盖)

        供 _replace_variables / resolver 使用
        """
        result: Dict[str, Any] = {}
        for scope in VALID_SCOPES:
            result.update(self._layers[scope])
        return result

    # ---------- 作用域管理 ----------

    def load_environment(self, env_variables: Dict[str, Any]) -> None:
        """加载 Environment 表的变量到 L2(覆盖式)"""
        self._layers['environment'] = dict(env_variables or {})

    def load_globals(self, global_variables: Dict[str, Any]) -> None:
        """加载全局变量到 L1"""
        self._layers['global'] = dict(global_variables or {})

    def push_iteration(self, iter_vars: Optional[Dict[str, Any]] = None,
                        iter_index: int = 0) -> int:
        """进入一次新的 DDT 迭代

        将当前 L4 入栈,然后重置为新的迭代变量。
        返回入栈前的栈深度(用于 pop 时校验)。
        """
        self._iteration_stack.append({
            'vars': self._layers['iteration'],
            'index': getattr(self, '_iteration_index', 0),
        })
        self._layers['iteration'] = dict(iter_vars or {})
        self._iteration_index = iter_index
        return len(self._iteration_stack)

    def pop_iteration(self) -> Optional[Dict[str, Any]]:
        """退出当前迭代,恢复上一层"""
        if not self._iteration_stack:
            return None
        frame = self._iteration_stack.pop()
        self._layers['iteration'] = frame['vars']
        self._iteration_index = frame['index']
        return frame

    @property
    def iteration_index(self) -> int:
        return getattr(self, '_iteration_index', 0)

    def clear_request_scope(self) -> None:
        """请求开始前清空 L5"""
        self._layers['request'] = {}

    # ---------- 日志 ----------

    def log(self, event: str, **fields: Any) -> None:
        """记录执行期事件(提取失败、脚本异常等)"""
        entry = {'event': event}
        entry.update(fields)
        self.logs.append(entry)

    # ---------- 调试 ----------

    def snapshot(self) -> Dict[str, Any]:
        """返回各层变量快照,供日志与调试使用"""
        return {
            scope: dict(self._layers[scope])
            for scope in VALID_SCOPES
        }
