from django.urls import path
from . import views

app_name = "ventas"

urlpatterns = [
    path("impresion/", views.configurar_impresion, name="configurar_impresion"),
    path("nueva/", views.pos, name="pos"),
    path("buscar/", views.buscar, name="buscar"),
    path("carrito/agregar/", views.carrito_agregar, name="carrito_agregar"),
    path("carrito/actualizar/", views.carrito_actualizar, name="carrito_actualizar"),
    path("carrito/quitar/", views.carrito_quitar, name="carrito_quitar"),
    path("carrito/vaciar/", views.carrito_vaciar, name="carrito_vaciar"),
    path("confirmar/", views.confirmar, name="confirmar"),
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/comprobante/", views.comprobante, name="comprobante"),
    path("<int:pk>/comprobante/imagen/", views.imagen_comprobante, name="comprobante_imagen"),
    path("<int:pk>/comprobante/pdf/", views.pdf_comprobante, name="comprobante_pdf"),
    path("<int:pk>/comprobante/imprimir-escpos/", views.imprimir_escpos, name="comprobante_escpos"),
]
