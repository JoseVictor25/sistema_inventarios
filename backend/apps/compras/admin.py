"""Admin de compras: Proveedor, Compra y DetalleCompra."""
from django.contrib import admin

from apps.core.admin import SoloLecturaAdminMixin

from .models import Compra, DetalleCompra, Proveedor


class DetalleCompraInline(SoloLecturaAdminMixin, admin.TabularInline):
    model = DetalleCompra
    extra = 0
    fields = ["producto", "cantidad_unidades", "costo_unitario", "subtotal"]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Proveedor)
class ProveedorAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["nombre", "tipo", "telefono", "origen", "activo"]
    list_filter = ["tipo", "activo"]
    search_fields = ["nombre", "contacto", "telefono"]


@admin.register(Compra)
class CompraAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["id", "proveedor", "fecha", "total", "usuario"]
    list_filter = ["fecha", "proveedor"]
    search_fields = ["proveedor__nombre", "observacion"]
    inlines = [DetalleCompraInline]

    def has_delete_permission(self, request, obj=None):
        # Evita borrado accidental de registros históricos desde el admin
        return False


@admin.register(DetalleCompra)
class DetalleCompraAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["compra", "producto", "cantidad_unidades", "costo_unitario", "subtotal"]
    search_fields = ["compra__id", "producto__nombre"]

    def has_delete_permission(self, request, obj=None):
        return False
