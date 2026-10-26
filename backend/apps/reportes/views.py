"""Pantallas y descargas de solo lectura, sin cálculos de negocio."""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET
from apps.core.exceptions import ErrorDeNegocio
from apps.core.permissions import tiene_permiso
from . import services, exportadores
from .forms import FiltrosReporteForm


@login_required
@require_GET
def inicio(request):
    disponibles = [dict(titulo=v[0], url=reverse('reportes:' + n)) for n, v in services.REPORTES.items() if all(tiene_permiso(request.user, p) for p in v[1])]
    if not disponibles:
        raise PermissionDenied('No tienes permiso para consultar reportes.')
    return render(request, 'reportes/inicio.html', {'reportes': disponibles})


@login_required
@require_GET
def reporte(request, nombre, exportar=False):
    services.autorizar_reporte(request.user, nombre)
    datos = request.GET.copy()
    formato = None
    if exportar:
        formatos = datos.pop('formato', [])
        if len(formatos) != 1 or formatos[0] not in ('xlsx', 'pdf'):
            return HttpResponse('Formato inválido. Elige xlsx o pdf.', status=422)
        formato = formatos[0]
    inicial = not datos and not exportar and nombre not in ('inventario_valorizado', 'vencimientos')
    if not datos and nombre == 'vencimientos':
        datos['dias'] = str(settings.DIAS_ALERTA_VENCIMIENTO)
    form = FiltrosReporteForm(nombre, None if inicial else datos, initial={'agrupar': 'dia'})
    contexto = dict(titulo=services.REPORTES[nombre][0], form_filtros=form, nombre=nombre)
    estado = 200
    if not inicial:
        if form.is_valid():
            try:
                resultado = services.consultar_reporte(request.user, nombre, datos)
            except ErrorDeNegocio as error:
                form.add_error(None, error.mensaje)
                estado = 422
            else:
                if exportar:
                    contenido = (exportadores.exportar_excel if formato == 'xlsx' else exportadores.exportar_pdf)(resultado, usuario=request.user)
                    sufijo = f'_{form.cleaned_data["desde"].isoformat()}_a_{form.cleaned_data["hasta"].isoformat()}' if 'desde' in form.cleaned_data else '_actual'
                    respuesta = HttpResponse(contenido, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if formato == 'xlsx' else 'application/pdf')
                    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}{sufijo}.{formato}"'
                    respuesta['Cache-Control'] = 'private, no-store'
                    return respuesta
                contexto.update(resultado)
                contexto['tabla'] = [[dict(texto=exportadores.texto_celda(v, c[2]), tipo=c[2]) for v, c in zip(fila, resultado['columnas'])] for fila in exportadores.matriz(resultado)]
                contexto['pie'] = ['Totales'] + [exportadores.texto_celda(resultado['totales'].get(k), t) for k, _, t in resultado['columnas'][1:]]
                contexto['url_exportar'] = reverse('reportes:' + nombre + '_exportar')
                contexto['filtros_query'] = datos.urlencode()
                contexto['consultado'] = True
        else:
            estado = 422
    respuesta = render(request, f'reportes/{nombre}.html', contexto, status=estado)
    respuesta['Cache-Control'] = 'private, no-store'
    return respuesta
