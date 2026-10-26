from django.urls import path
from . import views
from .services import REPORTES

app_name = "reportes"
urlpatterns = [path('', views.inicio, name='inicio')]
for nombre in REPORTES:
    urlpatterns += [
        path(f'{nombre}/', views.reporte, {'nombre': nombre}, name=nombre),
        path(f'{nombre}/exportar/', views.reporte, {'nombre': nombre, 'exportar': True}, name=nombre + '_exportar'),
    ]
