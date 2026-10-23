from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("", include("apps.usuarios.urls")),
    path("catalogo/", include("apps.catalogo.urls")),
    path("compras/", include("apps.compras.urls")),
    path("inventario/", include("apps.inventario.urls")),
    path("ventas/", include("apps.ventas.urls")),
    path("caja/", include("apps.caja.urls")),
    path("reportes/", include("apps.reportes.urls")),
    path("auditoria/", include("apps.auditoria.urls")),
]
