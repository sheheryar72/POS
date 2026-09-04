from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import service_worker

urlpatterns = [
    path('admin/', admin.site.urls),

    # Served from the root path (not /static/...) so the service worker's
    # scope covers the whole app — a service worker can only control pages
    # at or below the path it's served from.
    path('sw.js', service_worker, name='service_worker'),

    path('', include('orders.urls')),
    path('', include('menu.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
