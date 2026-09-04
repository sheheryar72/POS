from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.PosLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),

    path('', views.pos_screen, name='pos_screen'),
    path('kitchen/', views.kitchen_screen, name='kitchen_screen'),
    path('history/', views.orders_history_screen, name='orders_history_screen'),
    path('dashboard/', views.dashboard_screen, name='dashboard_screen'),

    path('api/menu/', views.api_menu, name='api_menu'),
    path('api/orders/place/', views.api_place_order, name='api_place_order'),
    path('api/orders/sync/', views.api_sync_order, name='api_sync_order'),
    path('api/orders/queue/', views.api_orders_queue, name='api_orders_queue'),
    path('api/orders/history/', views.api_orders_history, name='api_orders_history'),
    path('api/orders/<int:order_id>/', views.api_order_detail, name='api_order_detail'),
    path('api/orders/<int:order_id>/status/', views.api_update_order_status, name='api_update_order_status'),
    path('api/dashboard/summary/', views.api_dashboard_summary, name='api_dashboard_summary'),
]
