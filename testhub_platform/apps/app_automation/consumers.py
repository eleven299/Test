import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class AppExecutionConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        try:
            # 检查用户是否已认证
            user = self.scope.get("user")
            if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
                logger.warning(f"WebSocket 拒绝未认证连接")
                await self.close()
                return

            self.execution_id = self.scope["url_route"]["kwargs"]["execution_id"]
            self.group_name = f"app_execution_{self.execution_id}"

            # 检查用户是否有权访问该执行记录
            from .models import AppTestExecution, AppProject
            from django.db.models import Q

            try:
                execution = await AppTestExecution.objects.select_related(
                    'test_case__project'
                ).aget(id=self.execution_id)
            except AppTestExecution.DoesNotExist:
                logger.warning(f"WebSocket 执行记录不存在: execution_id={self.execution_id}")
                await self.close()
                return

            project = getattr(execution.test_case, 'project', None)
            if project:
                has_access = await AppProject.objects.filter(
                    Q(id=project.id) & (Q(owner=user) | Q(members=user))
                ).aexists()
                if not has_access:
                    logger.warning(f"WebSocket 用户 {user.username} 无权访问执行 {self.execution_id}")
                    await self.close()
                    return

            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            logger.info(f"WebSocket 连接成功: execution_id={self.execution_id}, user={user.username}")
        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            await self.close()

    async def disconnect(self, close_code):
        try:
            if hasattr(self, 'group_name'):
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
                logger.info(f"WebSocket 断开: execution_id={self.execution_id}, code={close_code}")
        except Exception as e:
            logger.error(f"WebSocket 断开处理失败: {e}")

    async def execution_update(self, event):
        try:
            await self.send_json(event)
        except Exception as e:
            logger.error(f"WebSocket 推送消息失败: {e}")
