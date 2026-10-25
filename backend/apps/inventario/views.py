"""Cinco pantallas de inventario; consultas y escrituras autorizadas en servicios."""
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_http_methods
from apps.core.permissions import permiso_requerido, tiene_permiso
from apps.core.exceptions import ErrorDeNegocio
from . import services
from .models import Lote
from .forms import (FiltroStockForm, FiltroLoteForm, FiltroMovimientoForm,
                    FiltroAlertasForm, AjusteInventarioForm)


def _lista(request, clase, servicio, plantilla):
    form = clase(request.GET)
    pagina = None
    if form.is_valid():
        try:
            pagina = servicio(request.user, request.GET)
        except ErrorDeNegocio as error:
            form.add_error(None, error.mensaje)
    filtros = request.GET.copy()
    filtros.pop('page', None)
    return render(request, plantilla, {'form': form, 'page_obj': pagina,
        'q': request.GET.get('q', ''), 'filtros_query': filtros.urlencode(),
        'mostrar_costos': tiene_permiso(request.user, 'ver_costos')}, status=200 if pagina is not None else 422)


@permiso_requerido('ver_stock')
@require_GET
def stock_lista(request):
    return _lista(request, FiltroStockForm, services.listar_stock, 'inventario/stock_lista.html')


@permiso_requerido('ver_stock')
@require_GET
def lote_lista(request):
    return _lista(request, FiltroLoteForm, services.listar_lotes, 'inventario/lote_lista.html')


@permiso_requerido('ver_stock')
@require_GET
def movimiento_lista(request):
    return _lista(request, FiltroMovimientoForm, services.listar_movimientos, 'inventario/movimiento_lista.html')


@permiso_requerido('ver_stock')
@require_GET
def alertas(request):
    form = FiltroAlertasForm(request.GET)
    contexto = {'form': form, 'mostrar_costos': tiene_permiso(request.user, 'ver_costos')}
    if form.is_valid():
        contexto.update(services.obtener_alertas(usuario=request.user, filtros=request.GET))
        grupos = []
        for nombre, parametro, titulo in [('stock_bajo', 'page_bajo', 'Stock bajo'),
                ('por_vencer', 'page_por_vencer', 'Por vencer'), ('vencidos', 'page_vencidos', 'Vencidos con stock')]:
            pagina = contexto[nombre]
            enlaces = {}
            for sentido in ('previous', 'next'):
                if getattr(pagina, 'has_' + sentido)():
                    consulta = request.GET.copy()
                    consulta[parametro] = getattr(pagina, sentido + '_page_number')()
                    enlaces[sentido] = '?' + consulta.urlencode()
            grupos.append({'nombre': nombre, 'titulo': titulo, 'pagina': pagina, **enlaces})
        contexto['grupos'] = grupos
    return render(request, 'inventario/alertas.html', contexto, status=200 if form.is_valid() else 422)


@permiso_requerido('ajustar_inventario')
@require_http_methods(['GET', 'POST'])
def ajuste_crear(request):
    form = AjusteInventarioForm(request.POST if request.method == 'POST' else None,
                                initial={'lote': request.GET.get('lote')})
    seleccionado = None
    if request.method == 'POST' and form.is_valid():
        try:
            movimiento = services.ajustar_inventario(request.user, **form.cleaned_data)
        except ErrorDeNegocio as error:
            form.add_error(None, error.mensaje)
        else:
            messages.success(request, f'{movimiento.get_tipo_display()} registrado en el lote {movimiento.lote.codigo_lote}.')
            # POST/Redirect/GET no equivale a idempotencia persistente.
            return redirect(f"/inventario/ajuste/?lote={movimiento.lote_id}")
    identificador = form.cleaned_data.get('lote') if form.is_bound else request.GET.get('lote')
    if identificador:
        try:
            identificador = int(identificador)
            if not 0 < identificador <= 9223372036854775807:
                raise ValueError
            seleccionado = services.obtener_lote_para_ajuste(request.user, identificador)
        except (ValueError, ErrorDeNegocio):
            if not form.is_bound:
                form = AjusteInventarioForm({'lote': identificador})
                form.is_valid()
            form.add_error('lote', 'El lote indicado no existe o no es válido.')
    lotes_disponibles = list(
        Lote.objects.order_by('producto__nombre', 'codigo_lote').values(
            'id', 'codigo_lote', 'producto__nombre', 'producto__codigo',
            'cantidad_actual', 'cantidad_inicial', 'fecha_vencimiento'
        )[:300]
    )
    return render(request, 'inventario/ajuste_form.html', {
        'form': form,
        'lotes': [seleccionado] if seleccionado else [],
        'lote_seleccionado': seleccionado,
        'lotes_disponibles': lotes_disponibles,
    }, status=422 if form.errors else 200)
