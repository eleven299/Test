"""
Django management command: run_api_suite

用法:
    python manage.py run_api_suite <suite_id_or_name> \
        [--environment=ENV_ID] \
        [--trigger=cli|ci] \
        [--fail-fast] \
        [--output=none|json|junit] \
        [--output-file=PATH] \
        [--no-snapshots] \
        [--quiet]

退出码(CI 集成关键):
    0   全部步骤通过
    1   存在失败或错误步骤
    2   执行前异常(套件不存在 / 参数错误)

CI 集成示例(GitLab):
    api-test:
      stage: test
      script:
        - python manage.py run_api_suite "登录回归" --trigger=ci
            --output=junit --output-file=report.xml
      artifacts:
        when: always
        reports:
          junit: report.xml
"""
import sys
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.api_testing.models import TestSuite, Environment
from apps.api_testing.engine import TestExecutionEngine
from apps.api_testing.reporters import build_report, write_report


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '执行接口自动化测试套件(CLI / CI 入口)'

    EXIT_PASS = 0
    EXIT_FAIL = 1
    EXIT_ERROR = 2

    def add_arguments(self, parser):
        parser.add_argument(
            'suite',
            type=str,
            help='测试套件 ID 或 名称(名称需全局唯一,否则需用 ID)',
        )
        parser.add_argument(
            '--environment', '-e',
            type=int,
            default=None,
            help='环境变量 ID,覆盖套件默认环境',
        )
        parser.add_argument(
            '--trigger', '-t',
            type=str,
            default='cli',
            choices=['cli', 'ci', 'manual'],
            help='触发来源标记,默认 cli',
        )
        parser.add_argument(
            '--fail-fast',
            action='store_true',
            default=False,
            help='命令行强制启用 fail-fast(覆盖套件配置)',
        )
        parser.add_argument(
            '--output', '-o',
            type=str,
            default='none',
            choices=['none', 'json', 'junit'],
            help='报告输出格式,默认 none(仅控制台摘要)',
        )
        parser.add_argument(
            '--output-file',
            type=str,
            default=None,
            help='报告输出文件路径,不指定则输出到 stdout',
        )
        parser.add_argument(
            '--no-snapshots',
            action='store_true',
            default=False,
            help='JSON 报告不包含请求/响应快照(减小体积)',
        )
        parser.add_argument(
            '--quiet', '-q',
            action='store_true',
            default=False,
            help='静默模式,只输出错误与摘要',
        )

    def handle(self, *args, **options):
        suite_spec = options['suite']
        env_id = options.get('environment')
        trigger = options.get('trigger') or 'cli'
        fail_fast_override = options.get('fail_fast')
        output_fmt = options.get('output') or 'none'
        output_file = options.get('output_file')
        include_snapshots = not options.get('no_snapshots')
        quiet = options.get('quiet')

        # 1. 解析套件
        try:
            suite = self._resolve_suite(suite_spec)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[错误] {e}"))
            sys.exit(self.EXIT_ERROR)

        # 2. 解析环境(可选)
        environment = suite.environment
        if env_id:
            environment = Environment.objects.filter(id=env_id).first()
            if environment is None:
                self.stderr.write(self.style.ERROR(
                    f"[错误] 环境 ID={env_id} 不存在"
                ))
                sys.exit(self.EXIT_ERROR)

        # 3. 命令行覆盖 fail_fast
        if fail_fast_override and not suite.fail_fast:
            suite.fail_fast = True
            # 内存修改即可,不写库
            self.stdout.write(self.style.WARNING(
                "[提示] 命令行强制启用 fail-fast"
            ))

        if not quiet:
            self.stdout.write(self.style.SUCCESS(
                f"开始执行:套件「{suite.name}」(id={suite.id}),触发={trigger}"
            ))

        # 4. 调用引擎
        engine = TestExecutionEngine(
            test_suite=suite,
            environment=environment,
            user=suite.created_by,
            trigger_source=trigger,
            persist_history=not quiet,  # 静默模式下不污染历史
        )

        try:
            execution = engine.run()
        except Exception as e:
            logger.exception("套件执行异常")
            self.stderr.write(self.style.ERROR(f"[异常] {e}"))
            sys.exit(self.EXIT_ERROR)

        # 5. 输出报告
        if output_fmt != 'none':
            try:
                content = build_report(execution, fmt=output_fmt,
                                        include_snapshots=include_snapshots)
                if output_file:
                    write_report(output_file, content)
                    if not quiet:
                        self.stdout.write(self.style.SUCCESS(
                            f"报告已写入: {output_file}"
                        ))
                else:
                    self.stdout.write(content)
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"[警告] 报告生成失败: {e}"
                ))

        # 6. 控制台摘要
        if not quiet:
            self._print_summary(execution)

        # 7. 退出码
        if execution.status == 'COMPLETED':
            sys.exit(self.EXIT_PASS)
        sys.exit(self.EXIT_FAIL)

    # ---------- 辅助 ----------

    def _resolve_suite(self, spec: str) -> TestSuite:
        # 1. 数字优先按 ID
        if spec.isdigit():
            suite = TestSuite.objects.filter(id=int(spec)).first()
            if suite:
                return suite
            raise CommandError(f"按 ID 未找到套件: {spec}")

        # 2. 按名称精确匹配
        matched = TestSuite.objects.filter(name=spec)
        if matched.count() == 1:
            return matched.first()
        if matched.count() > 1:
            raise CommandError(
                f"按名称找到 {matched.count()} 个同名套件,请改用 ID: "
                f"{', '.join(str(s.id) for s in matched)}"
            )

        # 3. 按名称模糊匹配(Icontains)
        fuzzy = TestSuite.objects.filter(name__icontains=spec)
        if fuzzy.count() == 1:
            return fuzzy.first()
        if fuzzy.count() > 1:
            names = ', '.join(f"{s.name}(id={s.id})" for s in fuzzy[:10])
            raise CommandError(
                f"模糊匹配到 {fuzzy.count()} 个套件,请使用更精确的名称或 ID: {names}"
            )

        raise CommandError(f"未找到套件: {spec}")

    def _print_summary(self, execution) -> None:
        total = execution.total_requests or 0
        passed = execution.passed_requests or 0
        failed = execution.failed_requests or 0

        duration = ''
        if execution.start_time and execution.end_time:
            duration = f', 耗时 {(execution.end_time - execution.start_time).total_seconds():.2f}s'

        line = (f"摘要: 总计 {total}, 通过 {passed}, 失败 {failed}"
                f", 状态={execution.status}{duration}")
        if failed == 0 and execution.status == 'COMPLETED':
            self.stdout.write(self.style.SUCCESS(line))
        else:
            self.stdout.write(self.style.ERROR(line))

        if execution.stop_reason:
            self.stdout.write(self.style.WARNING(
                f"停止原因: {execution.stop_reason}"
            ))
