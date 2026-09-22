from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import MobileTokenObtainPairSerializer


class MobileTokenObtainPairView(TokenObtainPairView):
    serializer_class = MobileTokenObtainPairSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """
    Mirrors what TenantMiddleware/UserProfile already expose server-side —
    lets the mobile app render the right screens (owner-only tabs, plan-
    gated features) without duplicating that logic client-side.
    """
    profile = request.user.profile
    restaurant = profile.restaurant
    return Response({
        'username': request.user.username,
        'role': profile.role,
        'restaurant': {
            'name': restaurant.name,
            'address': restaurant.address,
            'phone': restaurant.phone,
            'currency_symbol': restaurant.currency_symbol,
            'tax_percent': str(restaurant.tax_percent),
            'receipt_footer_note': restaurant.receipt_footer_note,
            'has_inventory': restaurant.has_feature('has_inventory'),
            'has_reports': restaurant.has_feature('has_reports'),
        },
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    Revokes the refresh token server-side (blacklist) so it can't be reused
    if the device is later compromised — the access token still expires on
    its own short lifetime either way, see SIMPLE_JWT in core/settings.py.
    """
    refresh_token = request.data.get('refresh')
    if not refresh_token:
        return Response({'error': 'refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        RefreshToken(refresh_token).blacklist()
    except TokenError:
        pass  # already invalid/expired/blacklisted — logout still succeeds
    return Response(status=status.HTTP_205_RESET_CONTENT)
