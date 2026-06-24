from django.conf import settings
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include, re_path
from django.views.static import serve as serve_static

urlpatterns = [
    path('', lambda request: redirect('iqa:login_redirect')),
    path('admin/', admin.site.urls),
    path('iqa/', include('iqa.urls')),
]

if settings.SERVE_MEDIA_FILES:
    urlpatterns += [
        re_path(
            r'^media/(?P<path>.*)$',
            serve_static,
            {'document_root': settings.MEDIA_ROOT},
        )
    ]
