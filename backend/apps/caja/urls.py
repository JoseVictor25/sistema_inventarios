from django.urls import path
from . import views

app_name = "caja"
urlpatterns = [
    path("", views.estado, name="estado"),
    path("abrir/", views.abrir, name="abrir"),
    path("movimientos/nuevo/", views.movimiento_crear, name="movimiento_crear"),
    path("cerrar/", views.cerrar, name="cerrar"),
    path("historial/", views.historial, name="historial"),
]
