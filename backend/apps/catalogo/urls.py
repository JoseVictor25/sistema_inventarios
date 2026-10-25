from django.urls import path
from . import views

app_name = "catalogo"
urlpatterns = [
    path("categorias/", views.categoria_lista, name="categoria_lista"),
    path("categorias/nueva/", views.categoria_form, name="categoria_crear"),
    path("categorias/<int:pk>/editar/", views.categoria_form, name="categoria_editar"),
    path("productos/", views.producto_lista, name="producto_lista"),
    path("productos/nuevo/", views.producto_form, name="producto_crear"),
    path("productos/<int:pk>/editar/", views.producto_form, name="producto_editar"),
    path("productos/<int:pk>/", views.producto_detalle, name="producto_detalle"),
    path("productos/<int:pk>/desactivar/", views.producto_desactivar, name="producto_desactivar"),
    path("productos/<int:pk>/presentaciones/nueva/", views.presentacion_crear, name="presentacion_crear"),
    path("presentaciones/<int:pk>/precio/", views.presentacion_precio, name="presentacion_precio"),
    path("productos/<int:pk>/atributos/nuevo/", views.atributo_crear, name="atributo_crear"),
    path("productos/<int:pk>/atributos/<int:atributo_pk>/editar/", views.atributo_editar, name="atributo_editar"),
]
