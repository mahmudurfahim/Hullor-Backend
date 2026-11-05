from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView


def root(request):
    return JsonResponse({"name": "HULLOR API", "status": "ok", "docs": "/api/", "admin": "/admin/"})


urlpatterns = [
    path("", root),
    path("admin/", admin.site.urls),  # Django admin → https://<backend>/admin/
    path("django-admin/", RedirectView.as_view(url="/admin/", permanent=False)),  # পুরনো লিংক
    path("api/", include("accounts.urls")),
    path("api/", include("store.urls")),
    path("api/admin/", include("store.admin_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
