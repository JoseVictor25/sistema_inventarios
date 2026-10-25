"""Admin del inventario: Lote y MovimientoInventario."""
from django.contrib import admin

from apps.core.admin import SoloLecturaAdminMixin, ConsultaCostosAdminMixin

from .models import Lote, MovimientoInventario, OperacionAjusteInventario


@admin.register(Lote)
class LoteAdmin(ConsultaCostosAdminMixin, SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = [
        "codigo_lote",
        "producto",
        "cantidad_actual",
        "cantidad_inicial",
        "costo_unitario",
        "fecha_vencimiento",
    ]
    list_filter = ["fecha_vencimiento", "producto"]
    search_fields = ["codigo_lote", "producto__nombre", "producto__codigo"]
    readonly_fields = ["cantidad_inicial"]

    def has_delete_permission(self, request, obj=None):
        # Los lotes representan historial de compras e inventario
        return False


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["id", "lote", "tipo", "cantidad", "fecha", "motivo", "usuario"]
    list_filter = ["tipo", "fecha"]
    search_fields = ["lote__codigo_lote", "lote__producto__nombre", "motivo"]
    readonly_fields = ["lote", "tipo", "cantidad", "fecha", "motivo", "usuario"]

    def has_add_permission(self, request):
        # El servicio crea movimiento y stock juntos; nunca un alta aislada.
        return False

    def has_change_permission(self, request, obj=None):
        # RN-19: inmutable
        return False

    def has_delete_permission(self, request, obj=None):
        # RN-19: inmutable
        return False


@admin.register(OperacionAjusteInventario)
class OperacionAjusteInventarioAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["clave", "usuario", "lote", "tipo", "huella", "creado_en"]
    list_filter = ["tipo", "creado_en"]
    search_fields = ["clave", "usuario__username", "huella", "lote__codigo_lote"]
    readonly_fields = ["clave", "usuario", "lote", "tipo", "huella", "movimiento", "auditoria", "creado_en"]
