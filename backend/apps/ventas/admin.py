"""Admin de ventas: MetodoPago, Venta, DetalleVenta, DetalleVentaLote y Pago."""
from django.contrib import admin

from apps.core.admin import SoloLecturaAdminMixin

from .models import DetalleVenta, DetalleVentaLote, MetodoPago, Pago, Venta


class DetalleVentaInline(SoloLecturaAdminMixin, admin.TabularInline):
    model = DetalleVenta
    extra = 0
    fields = [
        "presentacion",
        "cantidad_presentaciones",
        "unidades_totales",
        "precio_aplicado",
        "subtotal",
    ]
    readonly_fields = ["precio_aplicado", "subtotal", "unidades_totales"]

    def has_delete_permission(self, request, obj=None):
        return False


class PagoInline(SoloLecturaAdminMixin, admin.TabularInline):
    model = Pago
    extra = 0
    fields = ["metodo", "monto", "referencia"]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "es_efectivo", "activo"]
    list_filter = ["es_efectivo", "activo"]
    search_fields = ["nombre"]


@admin.register(Venta)
class VentaAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["id", "caja", "fecha", "total", "usuario"]
    list_filter = ["fecha", "caja"]
    search_fields = ["id", "usuario__username"]
    inlines = [DetalleVentaInline, PagoInline]

    def has_delete_permission(self, request, obj=None):
        # Historial de ventas protegido contra borrado accidental
        return False


@admin.register(DetalleVenta)
class DetalleVentaAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = [
        "id",
        "venta",
        "presentacion",
        "cantidad_presentaciones",
        "unidades_totales",
        "precio_aplicado",
        "subtotal",
    ]
    search_fields = ["venta__id", "presentacion__nombre"]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DetalleVentaLote)
class DetalleVentaLoteAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["id", "detalle_venta", "lote", "cantidad_unidades"]
    search_fields = ["lote__codigo_lote", "detalle_venta__venta__id"]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Pago)
class PagoAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["id", "venta", "metodo", "monto", "referencia"]
    list_filter = ["metodo"]
    search_fields = ["venta__id", "referencia"]

    def has_delete_permission(self, request, obj=None):
        return False
