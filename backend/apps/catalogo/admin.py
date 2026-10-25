"""Admin del catálogo: Categoria, Producto, Presentacion y AtributoProducto."""
from django.contrib import admin
from apps.core.admin import SoloLecturaAdminMixin

from .models import AtributoProducto, Categoria, Presentacion, Producto


class PresentacionInline(SoloLecturaAdminMixin, admin.TabularInline):
    model = Presentacion
    extra = 1
    fields = ["nombre", "unidades_equivalentes", "precio_venta", "activa"]


class AtributoInline(SoloLecturaAdminMixin, admin.TabularInline):
    model = AtributoProducto
    extra = 1
    fields = ["nombre", "valor"]


@admin.register(Categoria)
class CategoriaAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["nombre", "padre", "activa"]
    list_filter = ["activa"]
    search_fields = ["nombre"]


@admin.register(Producto)
class ProductoAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["codigo", "nombre", "categoria", "stock_actual", "stock_minimo", "activo"]
    list_filter = ["categoria", "activo"]
    search_fields = ["codigo", "nombre"]
    readonly_fields = ["stock_actual"]
    inlines = [PresentacionInline, AtributoInline]


@admin.register(Presentacion)
class PresentacionAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["producto", "nombre", "unidades_equivalentes", "precio_venta", "activa"]
    list_filter = ["activa"]
    search_fields = ["nombre", "producto__nombre"]


@admin.register(AtributoProducto)
class AtributoProductoAdmin(SoloLecturaAdminMixin, admin.ModelAdmin):
    list_display = ["producto", "nombre", "valor"]
    search_fields = ["nombre", "producto__nombre"]
