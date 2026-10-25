from django.urls import path
from . import views

app_name = "inventario"
urlpatterns = [
    path('', views.stock_lista, name='stock_lista'),
    path('lotes/', views.lote_lista, name='lote_lista'),
    path('alertas/', views.alertas, name='alertas'),
    path('ajuste/', views.ajuste_crear, name='ajuste_crear'),
    path('movimientos/', views.movimiento_lista, name='movimiento_lista'),
]
