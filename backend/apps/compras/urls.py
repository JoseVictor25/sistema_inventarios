"""Rutas de URLs para el módulo de compras y proveedores — Fase 4."""
from django.urls import path
from . import views

app_name = "compras"

urlpatterns = [
    # Compras
    path("", views.compra_lista, name="compra_lista"),
    path("nueva/", views.compra_crear, name="compra_crear"),
    path("nueva/linea/", views.compra_linea, name="compra_linea"),
    path("<int:pk>/", views.compra_detalle, name="compra_detalle"),
    # Proveedores
    path("proveedores/", views.proveedor_lista, name="proveedor_lista"),
    path("proveedores/nuevo/", views.proveedor_form, name="proveedor_crear"),
    path("proveedores/<int:pk>/editar/", views.proveedor_form, name="proveedor_editar"),
]
