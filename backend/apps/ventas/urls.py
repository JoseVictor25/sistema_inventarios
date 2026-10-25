from django.urls import path
from . import views

app_name = "ventas"

urlpatterns = [
    path("nueva/", views.pos, name="pos"),
    path("buscar/", views.buscar, name="buscar"),
    path("carrito/agregar/", views.carrito_agregar, name="carrito_agregar"),
    path("carrito/actualizar/", views.carrito_actualizar, name="carrito_actualizar"),
    path("carrito/quitar/", views.carrito_quitar, name="carrito_quitar"),
    path("carrito/vaciar/", views.carrito_vaciar, name="carrito_vaciar"),
    path("confirmar/", views.confirmar, name="confirmar"),
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.detalle, name="detalle"),
]
