"""Admin de auditoría: LogAuditoria (solo lectura)."""
from django.contrib import admin

from .models import LogAuditoria


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = ["fecha", "usuario", "accion", "entidad", "entidad_id"]
    list_filter = ["accion", "entidad", "fecha"]
    search_fields = ["usuario__username", "entidad", "accion"]
    readonly_fields = [
        "usuario",
        "fecha",
        "accion",
        "entidad",
        "entidad_id",
        "valor_anterior",
        "valor_nuevo",
    ]

    def has_add_permission(self, request):
        # Solo lectura: las entradas las crean los servicios
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
