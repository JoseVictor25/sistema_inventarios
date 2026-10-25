from django.urls import path
from . import views

app_name = "compras"
urlpatterns = [
    path("proveedores/", views.proveedor_lista, name="proveedor_lista"),
    path("proveedores/nuevo/", views.proveedor_form, name="proveedor_crear"),
    path("proveedores/<int:pk>/editar/", views.proveedor_form, name="proveedor_editar"),
]
