from django.urls import path

from . import views
from .primer_uso import primer_uso

app_name = "core"
urlpatterns = [
    path('configuracion-inicial/', primer_uso, name='primer_uso'),
    path("", views.inicio, name="inicio"),
    path('sistema/respaldos/', views.respaldos, name='respaldos'),
    path('sistema/respaldos/crear/', views.respaldo_crear, name='respaldo_crear'),
]
