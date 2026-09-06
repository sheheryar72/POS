from django.urls import path

from . import views

urlpatterns = [
    path('users/', views.manage_users_screen, name='manage_users_screen'),
    path('api/users/', views.api_manage_users, name='api_manage_users'),
    path('api/users/<int:user_id>/', views.api_manage_user_detail, name='api_manage_user_detail'),
]
