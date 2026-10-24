"""Admin de caja: Caja y MovimientoCaja."""
from django.contrib import admin

from .forms import MovimientoCajaAdminForm
from .models import Caja, MovimientoCaja


class MovimientoCajaInline(admin.TabularInline):
    model = MovimientoCaja
    form = MovimientoCajaAdminForm
    extra = 0
    fields = ["tipo", "monto", "concepto", "fecha", "usuario"]

    def has_add_permission(self, request, obj=None):
        return bool(obj and obj.estado == Caja.EstadoCaja.ABIERTA
                    and super().has_add_permission(request, obj))

    def has_change_permission(self, request, obj=None):
        return bool(obj and obj.estado == Caja.EstadoCaja.ABIERTA
                    and super().has_change_permission(request, obj))

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Caja)
class CajaAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "usuario",
        "estado",
        "fecha_apertura",
        "fecha_cierre",
        "monto_inicial",
        "monto_contado",
        "monto_esperado_display",
        "diferencia_display",
    ]
    list_filter = ["estado", "fecha_apertura"]
    search_fields = ["usuario__username", "observacion"]
    inlines = [MovimientoCajaInline]

    def has_change_permission(self, request, obj=None):
        if obj and obj.estado == Caja.EstadoCaja.CERRADA:
            return False
        return super().has_change_permission(request, obj)

    @admin.display(description="Monto Esperado")
    def monto_esperado_display(self, obj):
        return obj.monto_esperado()

    @admin.display(description="Diferencia")
    def diferencia_display(self, obj):
        dif = obj.diferencia()
        return dif if dif is not None else "—"

    def has_delete_permission(self, request, obj=None):
        # Registro financiero protegido contra borrado accidental
        return False


@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(admin.ModelAdmin):
    form = MovimientoCajaAdminForm
    list_display = ["id", "caja", "tipo", "monto", "concepto", "fecha", "usuario"]
    list_filter = ["tipo", "fecha"]
    search_fields = ["concepto", "caja__id"]

    def has_change_permission(self, request, obj=None):
        if obj and obj.caja.estado == Caja.EstadoCaja.CERRADA:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
