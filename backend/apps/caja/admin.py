"""Admin de caja: Caja y MovimientoCaja."""
from django.contrib import admin
from apps.core.admin import SoloLecturaAdminMixin

from .forms import MovimientoCajaAdminForm
from .models import Caja, MovimientoCaja, OperacionCaja


@admin.register(OperacionCaja)
class OperacionCajaAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["clave", "usuario", "accion", "caja", "movimiento", "creado_en"]


class MovimientoCajaInline(SoloLecturaAdminMixin, admin.TabularInline):
    model = MovimientoCaja
    form = MovimientoCajaAdminForm
    extra = 0
    fields = ["tipo", "monto", "concepto", "fecha", "usuario"]

@admin.register(Caja)
class CajaAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
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

    @admin.display(description="Monto Esperado")
    def monto_esperado_display(self, obj):
        from .services import _leer_resumen_guardado
        resumen = _leer_resumen_guardado(obj) if obj.estado == "CERRADA" else None
        if resumen:
            return resumen["esperado"]
        return obj.monto_esperado()

    @admin.display(description="Diferencia")
    def diferencia_display(self, obj):
        from .services import _leer_resumen_guardado
        resumen = _leer_resumen_guardado(obj) if obj.estado == "CERRADA" else None
        if resumen:
            return resumen["diferencia"]
        dif = obj.diferencia()
        return dif if dif is not None else "—"

    def has_delete_permission(self, request, obj=None):
        # Registro financiero protegido contra borrado accidental
        return False


@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    form = MovimientoCajaAdminForm
    list_display = ["id", "caja", "tipo", "monto", "concepto", "fecha", "usuario"]
    list_filter = ["tipo", "fecha"]
    search_fields = ["concepto", "caja__id"]

    def has_delete_permission(self, request, obj=None):
        return False
