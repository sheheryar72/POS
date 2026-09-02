from django.urls import path

from . import views

urlpatterns = [
    path('manage/', views.menu_manage_screen, name='menu_manage_screen'),

    path('api/manage/categories/', views.api_manage_categories, name='api_manage_categories'),
    path('api/manage/categories/<int:category_id>/', views.api_manage_category_detail, name='api_manage_category_detail'),
    path('api/manage/items/', views.api_manage_items, name='api_manage_items'),
    path('api/manage/items/<int:item_id>/', views.api_manage_item_detail, name='api_manage_item_detail'),
]
