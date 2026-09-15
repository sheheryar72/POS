from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

# Mounted at /api/auth/ — see core/urls.py. Additive only: the existing
# session-based /login/, /logout/ (orders/urls.py) are untouched and keep
# serving the web POS exactly as before.
urlpatterns = [
    path('token/', views.MobileTokenObtainPairView.as_view(), name='mobile_token_obtain'),
    path('token/refresh/', TokenRefreshView.as_view(), name='mobile_token_refresh'),
    path('me/', views.current_user, name='mobile_current_user'),
    path('logout/', views.logout, name='mobile_logout'),
]
