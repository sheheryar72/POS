import json

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .decorators import owner_required
from .models import UserProfile

User = get_user_model()


@owner_required
def manage_users_screen(request):
    return render(request, 'restaurants/manage_users.html')


def _serialize_user(user):
    profile = getattr(user, 'profile', None)
    return {
        'id': user.id,
        'username': user.username,
        'role': profile.role if profile else '',
        'role_display': profile.get_role_display() if profile else '',
        'is_active': user.is_active,
        'is_self': False,  # filled in by the caller, who knows the requesting user
        'date_joined': user.date_joined.strftime('%Y-%m-%d'),
    }


@owner_required
def api_manage_users(request):
    if request.method == 'GET':
        users = (
            User.objects.filter(profile__restaurant=request.restaurant)
            .select_related('profile')
            .order_by('username')
        )
        data = []
        for u in users:
            row = _serialize_user(u)
            row['is_self'] = (u.id == request.user.id)
            data.append(row)
        return JsonResponse({'users': data})

    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'error': 'Invalid request body.'}, status=400)

        username = (payload.get('username') or '').strip()
        password = payload.get('password') or ''
        role = payload.get('role') or UserProfile.Role.CASHIER

        if not username:
            return JsonResponse({'error': 'Username is required.'}, status=400)
        # Usernames are still globally unique (Django's built-in User.username
        # constraint) even though everything else is tenant-scoped — that's
        # a deliberate, acceptable limit given manual onboarding: two
        # different restaurants' staff can't pick the same username. Worth
        # revisiting only if self-signup makes username collisions common.
        if User.objects.filter(username__iexact=username).exists():
            return JsonResponse({'error': 'That username is already taken.'}, status=400)
        if role not in UserProfile.Role.values:
            return JsonResponse({'error': 'Invalid role.'}, status=400)

        try:
            validate_password(password)
        except ValidationError as e:
            return JsonResponse({'error': ' '.join(e.messages)}, status=400)

        user = User.objects.create_user(username=username[:150], password=password)
        UserProfile.objects.create(user=user, restaurant=request.restaurant, role=role)

        row = _serialize_user(user)
        return JsonResponse({'user': row}, status=201)

    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@owner_required
@require_http_methods(['POST', 'DELETE'])
def api_manage_user_detail(request, user_id):
    user = get_object_or_404(
        User.objects.select_related('profile'), id=user_id, profile__restaurant=request.restaurant
    )

    if user.id == request.user.id:
        return JsonResponse({'error': 'You cannot change your own account here.'}, status=400)

    if request.method == 'DELETE':
        user.delete()
        return JsonResponse({'ok': True})

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    if 'role' in payload:
        role = payload['role']
        if role not in UserProfile.Role.values:
            return JsonResponse({'error': 'Invalid role.'}, status=400)
        user.profile.role = role
        user.profile.save(update_fields=['role'])

    if 'is_active' in payload:
        user.is_active = bool(payload['is_active'])
        user.save(update_fields=['is_active'])

    if 'password' in payload and payload['password']:
        try:
            validate_password(payload['password'], user=user)
        except ValidationError as e:
            return JsonResponse({'error': ' '.join(e.messages)}, status=400)
        user.set_password(payload['password'])
        user.save(update_fields=['password'])

    row = _serialize_user(user)
    return JsonResponse({'user': row})
