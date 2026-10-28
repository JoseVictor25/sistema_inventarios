from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.inicio, name="inicio"),
    path('sistema/respaldos/', views.respaldos, name='respaldos'),
    path('sistema/respaldos/crear/', views.respaldo_crear, name='respaldo_crear'),
]
