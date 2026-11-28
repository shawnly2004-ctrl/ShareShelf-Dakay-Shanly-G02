import re

from django.contrib import admin
from django.urls import path, include
from django.urls import re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('', include('items.urls')),
]

handler404 = 'config.views.custom_404_view'
handler500 = 'config.views.custom_500_view'

def get_media_urlpatterns():
    if settings.DEBUG:
        return static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    if not settings.SERVE_MEDIA_FILES:
        return []
    media_prefix = re.escape(settings.MEDIA_URL.lstrip('/'))
    return [
        re_path(
            rf'^{media_prefix}(?P<path>.*)$',
            serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]


urlpatterns += get_media_urlpatterns()