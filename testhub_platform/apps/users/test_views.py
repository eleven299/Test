from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import re
from django.contrib.auth import get_user_model

User = get_user_model()


def _validate_phone(phone):
    """校验手机号格式（选填）"""
    if not phone:
        return True, ''  # 手机号选填
    if not re.match(r'^1[3-9]\d{9}$', phone):
        return False, '手机号格式不正确'
    return True, ''


@csrf_exempt
@require_http_methods(["POST"])
def test_register(request):
    try:
        data = json.loads(request.body)

        # 校验用户名格式：纯英文或纯数字或字母数字组合，不超过10位
        username = data.get('username', '').strip()
        if not username:
            return JsonResponse({
                'success': False,
                'error': '用户名不能为空'
            }, status=400)
        if len(username) > 10:
            return JsonResponse({
                'success': False,
                'error': '用户名不能超过10位'
            }, status=400)
        if not re.match(r'^[a-zA-Z0-9]+$', username):
            return JsonResponse({
                'success': False,
                'error': '用户名只能包含英文字母和数字'
            }, status=400)

        # 检查用户名是否已存在
        if User.objects.filter(username=username).exists():
            return JsonResponse({
                'success': False,
                'error': '用户名已存在'
            }, status=400)

        # 手机号校验（选填）
        phone = data.get('phone', '').strip()
        valid, error = _validate_phone(phone)
        if not valid:
            return JsonResponse({'success': False, 'error': error}, status=400)

        # 检查手机号是否已被注册（仅当填写了手机号时）
        if phone and User.objects.filter(phone=phone).exists():
            return JsonResponse({
                'success': False,
                'error': '该手机号已被注册'
            }, status=400)

        # 创建用户
        user = User.objects.create_user(
            username=username,
            email=data.get('email', ''),
            password=data.get('password'),
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            phone=phone,
            department=data.get('department', ''),
            position=data.get('position', '')
        )

        # 生成 JWT token
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)

        return JsonResponse({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'phone': user.phone,
                'first_name': user.first_name,
                'last_name': user.last_name
            },
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)