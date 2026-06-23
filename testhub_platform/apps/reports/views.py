from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q, Sum, F, Avg
from django.db.models.functions import TruncDate, Length
from django.utils import timezone
from datetime import timedelta, datetime
from .models import TestReport, ReportTemplate
from apps.executions.models import TestPlan, TestRun, TestRunCase
from apps.testcases.models import TestCase
from apps.requirement_analysis.models import RequirementAnalysis, GeneratedTestCase, BusinessRequirement
from apps.projects.models import Project


def _get_accessible_project_ids(user):
    return Project.objects.filter(
        Q(owner=user) | Q(members=user)
    ).distinct().values_list('id', flat=True)


class TestReportViewSet(viewsets.ViewSet):
    """测试报告视图集"""
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """获取概览数据"""
        accessible_ids = _get_accessible_project_ids(request.user)
        project_id = request.query_params.get('project')

        # 基础查询集（仅限用户可访问的项目）
        plans_qs = TestPlan.objects.filter(is_active=True, projects__in=accessible_ids).distinct()
        # 「用例总数」卡片口径：AI 生成的用例（testcases.is_ai_generated=True）
        ai_cases_qs = TestCase.objects.filter(
            is_ai_generated=True,
            project_id__in=accessible_ids
        )

        if project_id:
            # 确保请求的project_id在用户可访问范围内
            pid = int(project_id)
            if pid not in accessible_ids:
                return Response({'error': '项目不存在'}, status=404)
            plans_qs = plans_qs.filter(projects__id=pid)
            ai_cases_qs = ai_cases_qs.filter(project_id=pid)

        # 统计数据
        total_plans = plans_qs.count()
        total_cases = ai_cases_qs.count()

        # 一次性拉取所有相关 plan 下的 runs,避免 N+1 查询
        plans_ids = list(plans_qs.values_list('id', flat=True))
        runs_qs = TestRun.objects.filter(test_plan_id__in=plans_ids)

        # 计算测试计划总进度(基于 bulk_progress_stats,1 条 GROUP BY 查询)
        run_ids = list(runs_qs.values_list('id', flat=True))
        bulk_stats = TestRun.bulk_progress_stats(run_ids)
        progresses = [s['progress'] for s in bulk_stats.values()]
        avg_plan_progress = round(sum(progresses) / len(progresses), 1) if progresses else 0

        # 计算整体通过率(最近 10 次 run)
        recent_run_ids = list(runs_qs.order_by('-created_at').values_list('id', flat=True)[:10])
        recent_stats = TestRun.bulk_progress_stats(recent_run_ids)
        total_executed = sum(s['tested'] for s in recent_stats.values())
        total_passed = sum(s['passed'] for s in recent_stats.values())
        pass_rate = round((total_passed / total_executed * 100), 1) if total_executed > 0 else 0

        # 统计缺陷总数:单条聚合查询,避免双重 for 循环
        defects_rows = (
            TestRunCase.objects
            .filter(test_run_id__in=run_ids)
            .exclude(defects=[])
            .values_list('defects', flat=True)
        )
        defects_count = sum(len(d) for d in defects_rows if isinstance(d, list))
        
        return Response({
            'active_plans': total_plans,
            'plan_progress': avg_plan_progress,
            'total_cases': total_cases,
            'total_defects': defects_count,
            'pass_rate': pass_rate
        })

    @action(detail=False, methods=['get'])
    def status_distribution(self, request):
        """获取执行状态分布"""
        accessible_ids = _get_accessible_project_ids(request.user)
        project_id = request.query_params.get('project')
        version_id = request.query_params.get('version')

        runs_qs = TestRun.objects.filter(project_id__in=accessible_ids)
        if project_id:
            runs_qs = runs_qs.filter(project_id=project_id)
        if version_id:
            runs_qs = runs_qs.filter(version_id=version_id)
            
        distribution = TestRunCase.objects.filter(test_run__in=runs_qs).values('status').annotate(
            count=Count('id')
        )
        
        result = {item['status']: item['count'] for item in distribution}
        for status, _ in TestRunCase.STATUS_CHOICES:
            if status not in result:
                result[status] = 0
                
        return Response(result)

    @action(detail=False, methods=['get'])
    def defect_distribution(self, request):
        """获取缺陷分布 (按优先级)"""
        accessible_ids = _get_accessible_project_ids(request.user)
        project_id = request.query_params.get('project')
        qs = TestRunCase.objects.filter(status='failed', test_run__project_id__in=accessible_ids)

        if project_id:
            qs = qs.filter(test_run__project_id=project_id)
            
        distribution = qs.values('priority').annotate(count=Count('id'))
        
        # 映射优先级显示
        priority_map = dict(TestRunCase.PRIORITY_CHOICES)
        result = []
        for item in distribution:
            result.append({
                'name': priority_map.get(item['priority'], item['priority']),
                'value': item['count']
            })
            
        return Response(result)

    @action(detail=False, methods=['get'])
    def failed_cases_top(self, request):
        """获取失败用例TOP榜"""
        accessible_ids = _get_accessible_project_ids(request.user)
        project_id = request.query_params.get('project')

        qs = TestRunCase.objects.filter(status='failed', test_run__project_id__in=accessible_ids)
        if project_id:
            qs = qs.filter(test_run__project_id=project_id)
            
        # 按 testcase 分组统计失败次数
        top_failed = qs.values(
            'testcase__id', 'testcase__title'
        ).annotate(
            fail_count=Count('id')
        ).order_by('-fail_count')[:10]
        
        return Response(top_failed)

    @action(detail=False, methods=['get'])
    def execution_trend(self, request):
        """获取每日执行趋势"""
        accessible_ids = _get_accessible_project_ids(request.user)
        project_id = request.query_params.get('project')
        days = int(request.query_params.get('days', 7))

        current_tz = timezone.get_current_timezone()
        local_now = timezone.localtime(timezone.now())
        today = local_now.date()
        start_date = today - timedelta(days=days - 1)
        start_datetime = datetime.combine(start_date, datetime.min.time())
        start_datetime = timezone.make_aware(start_datetime, current_tz)

        qs = TestRunCase.objects.filter(
            executed_at__gte=start_datetime,
            status__in=['passed', 'failed', 'blocked', 'retest'],
            test_run__project_id__in=accessible_ids
        )

        if project_id:
            qs = qs.filter(test_run__project_id=project_id)
            
        # 由于数据库聚合(TruncDate)在某些环境下返回None，改为Python内存聚合
        # 获取所有符合条件的记录的执行时间
        executions = qs.values_list('executed_at', flat=True)
        
        # 初始化日期映射
        date_map = {}
        
        for executed_at in executions:
            if executed_at:
                # 转换为本地时间
                local_time = executed_at.astimezone(current_tz)
                date_str = local_time.date().strftime('%Y-%m-%d')
                date_map[date_str] = date_map.get(date_str, 0) + 1
        
        # 补全日期
        result = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            result.append({
                'date': date_str,
                'count': date_map.get(date_str, 0)
            })
            
        return Response(result)

    @action(detail=False, methods=['get'])
    def ai_efficiency(self, request):
        """获取AI效能分析"""
        accessible_ids = _get_accessible_project_ids(request.user)
        project_id = request.query_params.get('project')

        cases_qs = TestCase.objects.filter(project_id__in=accessible_ids)
        generated_qs = GeneratedTestCase.objects.filter(
            requirement__analysis__document__project_id__in=accessible_ids
        )
        requirements_qs = BusinessRequirement.objects.filter(
            analysis__document__project_id__in=accessible_ids
        )
        
        if project_id:
            cases_qs = cases_qs.filter(project_id=project_id)
            generated_qs = generated_qs.filter(requirement__analysis__document__project_id=project_id)
            requirements_qs = requirements_qs.filter(analysis__document__project_id=project_id)
            
        # 1. AI生成 vs 人工创建
        # 用 TestCase.is_ai_generated 在同一张表内统计，避免跨表减法导致数值不可靠
        ai_count = cases_qs.filter(is_ai_generated=True).count()
        manual_count = cases_qs.filter(is_ai_generated=False).count()
        total_cases = ai_count + manual_count

        # 生成采纳率：基于 AI 生成记录中已采纳（adopted）的比例
        generated_total = generated_qs.count()
        adopted_ai_count = generated_qs.filter(status='adopted').count()
        adoption_rate = round((adopted_ai_count / generated_total * 100), 1) if generated_total > 0 else 0
        
        # 3. 需求覆盖率
        total_reqs = requirements_qs.count()
        covered_reqs = generated_qs.filter(status='adopted').values('requirement').distinct().count()
        coverage_rate = round((covered_reqs / total_reqs * 100), 1) if total_reqs > 0 else 0
        
        # 4. 节省时间估算
        saved_hours = round(ai_count * 15 / 60, 1)
        
        return Response({
            'ai_vs_manual': {
                'ai': ai_count,
                'manual': manual_count
            },
            'adoption_rate': adoption_rate,
            'requirement_coverage': coverage_rate,
            'saved_hours': saved_hours
        })

    @action(detail=False, methods=['get'])
    def team_workload(self, request):
        """获取团队工作量"""
        accessible_ids = _get_accessible_project_ids(request.user)
        project_id = request.query_params.get('project')

        qs = TestRunCase.objects.filter(
            status__in=['passed', 'failed', 'blocked', 'retest'],
            executed_by__isnull=False,
            test_run__project_id__in=accessible_ids
        )

        if project_id:
            qs = qs.filter(test_run__project_id=project_id)
            
        # 统计执行数量
        execution_stats = qs.values(
            'executed_by__username'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # 统计发现缺陷数量
        defect_stats = {}
        defect_qs = qs.filter(status__in=['failed', 'blocked'])
        defect_data = defect_qs.values('executed_by__username').annotate(count=Count('id'))
        for item in defect_data:
            defect_stats[item['executed_by__username']] = item['count']
            
        result = []
        for item in execution_stats:
            username = item['executed_by__username']
            result.append({
                'username': username,
                'execution_count': item['count'],
                'defect_count': defect_stats.get(username, 0)
            })
            
        return Response(result)