from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='iqa:home', permanent=False)),
    path('admin/', admin.site.urls),
    path('iqa/', include('iqa.urls')),
] + static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT,
)


from django.urls import re_path
from django.views.static import serve as _serve_media

if getattr(settings, "SERVE_MEDIA_FILES", False):
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            _serve_media,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
