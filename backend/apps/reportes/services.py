"""Reportes autorizados con instantánea de lectura y cálculos Decimal.

SQLite no garantiza sumas monetarias exactas: se proyectan columnas mínimas y
se acumulan Decimal, sin joins que multipliquen pagos, detalles y salidas.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from django.db import transaction
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from django.utils import timezone
from apps.auditoria.models import LogAuditoria
from apps.caja.models import Caja, MovimientoCaja
from apps.catalogo.models import Producto
from apps.compras.models import Compra
from apps.core.exceptions import ErrorDeNegocio
from apps.core.operaciones import autorizar
from apps.inventario.models import Lote
from apps.ventas.models import Venta, Pago, DetalleVenta, DetalleVentaLote
from .forms import FiltrosReporteForm

ZONA = ZoneInfo('America/La_Paz')
CERO = Decimal('0.00')
# Clave, etiqueta y tipo gobiernan el formato, no los cálculos de negocio.
REPORTES = {
    'ventas': ('Ventas por período', ('ver_reportes',), [('periodo', 'Período', 'texto'), ('cantidad', 'Cantidad de ventas', 'entero'), ('total', 'Total', 'moneda')]),
    'ventas_metodo_pago': ('Ventas por método de pago', ('ver_reportes',), [('metodo', 'Método', 'texto'), ('cantidad', 'Ventas distintas por método', 'entero'), ('total', 'Total', 'moneda')]),
    'productos_mas_vendidos': ('Productos más vendidos', ('ver_reportes',), [('producto', 'Producto', 'texto'), ('unidades', 'Unidades base vendidas', 'entero'), ('total', 'Total', 'moneda')]),
    'compras': ('Compras', ('ver_reportes', 'ver_costos'), [('fecha', 'Fecha', 'fecha'), ('proveedor', 'Proveedor', 'texto'), ('total', 'Total', 'moneda')]),
    'inventario_valorizado': ('Inventario valorizado', ('ver_reportes', 'ver_costos'), [('producto', 'Producto', 'texto'), ('stock', 'Stock físico', 'entero'), ('costo', 'Costo unitario promedio', 'moneda'), ('valor', 'Valor', 'moneda')]),
    'ganancias': ('Ganancia bruta de mercadería', ('ver_reportes', 'ver_costos'), [('producto', 'Producto', 'texto'), ('ventas', 'Ventas', 'moneda'), ('costo', 'Costo vendido', 'moneda'), ('ganancia', 'Ganancia bruta', 'moneda')]),
    'vencimientos': ('Vencimientos próximos', ('ver_stock',), [('producto', 'Producto', 'texto'), ('lote', 'Lote', 'texto'), ('vence', 'Vencimiento', 'fecha'), ('stock', 'Stock', 'entero')]),
    'cierres_caja': ('Cierres de caja', ('ver_historial_caja',), [('fecha', 'Fecha de cierre', 'fecha'), ('turno', 'Turno', 'texto'), ('usuario', 'Responsable', 'texto'), ('esperado', 'Esperado', 'moneda'), ('contado', 'Contado', 'moneda'), ('diferencia', 'Diferencia', 'moneda')]),
}


def autorizar_reporte(usuario, nombre):
    """Autoriza antes de consultar o exportar datos."""
    if nombre not in REPORTES:
        raise ErrorDeNegocio('El reporte solicitado no existe.')
    for permiso in REPORTES[nombre][1]:
        autorizar(usuario, permiso)


def _rango(consulta, filtros, campo='fecha'):
    inicio = datetime.combine(filtros['desde'], time.min, ZONA)
    fin = datetime.combine(filtros['hasta'] + timedelta(days=1), time.min, ZONA)
    return consulta.filter(**{campo + '__gte': inicio, campo + '__lt': fin})


def _categoria(consulta, filtros, campo):
    categoria = filtros.get('categoria')
    return consulta.filter(**{campo: categoria.pk}) if categoria else consulta


def _ventas(f):
    truncar = {'dia': TruncDate, 'semana': TruncWeek, 'mes': TruncMonth}[f['agrupar']]
    consulta = _rango(Venta.objects.all(), f).annotate(periodo=truncar('fecha', tzinfo=ZONA))
    grupos = {}
    for periodo, total in consulta.order_by('periodo', 'pk').values_list('periodo', 'total').iterator():
        fecha = periodo.date() if isinstance(periodo, datetime) else periodo
        etiqueta = fecha.isoformat()
        if f['agrupar'] == 'semana':
            etiqueta = 'Semana desde lunes ' + etiqueta
        elif f['agrupar'] == 'mes':
            etiqueta = fecha.strftime('%Y-%m')
        fila = grupos.setdefault(etiqueta, dict(periodo=etiqueta, cantidad=0, total=CERO))
        fila['cantidad'] += 1
        fila['total'] += total
    return list(grupos.values()), []


def _metodos(f):
    consulta = _rango(Pago.objects.all(), f, 'venta__fecha')
    grupos, ventas = {}, set()
    for mid, nombre, vid, monto in consulta.order_by('metodo__nombre', 'metodo_id', 'pk').values_list('metodo_id', 'metodo__nombre', 'venta_id', 'monto').iterator():
        fila = grupos.setdefault(mid, dict(metodo=nombre, cantidad=0, total=CERO, ids=set()))
        fila['ids'].add(vid)
        ventas.add(vid)
        fila['total'] += monto
    for fila in grupos.values():
        fila['cantidad'] = len(fila.pop('ids'))
    return list(grupos.values()), [f'Ventas únicas del período: {len(ventas)}. Una venta mixta puede aparecer en varios conteos; los importes no se duplican.']


def _detalles(f):
    return _categoria(_rango(DetalleVenta.objects.all(), f, 'venta__fecha'), f, 'presentacion__producto__categoria_id')


def _productos(f):
    grupos = {}
    for pid, codigo, nombre, unidades, subtotal in _detalles(f).values_list('presentacion__producto_id', 'presentacion__producto__codigo', 'presentacion__producto__nombre', 'unidades_totales', 'subtotal').iterator():
        fila = grupos.setdefault(pid, dict(producto=f'{codigo} · {nombre}', unidades=0, total=CERO))
        fila['unidades'] += unidades
        fila['total'] += subtotal
    return sorted(grupos.values(), key=lambda x: (-x['unidades'], x['producto'])), []


def _compras(f):
    consulta = Compra.objects.filter(fecha__gte=f['desde'], fecha__lte=f['hasta'])
    if f.get('proveedor'):
        consulta = consulta.filter(proveedor=f['proveedor'])
    return [dict(fecha=fecha.isoformat(), proveedor=proveedor, total=total) for fecha, proveedor, total in consulta.order_by('fecha', 'pk').values_list('fecha', 'proveedor__nombre', 'total').iterator()], []


def _inventario(f):
    grupos = {}
    productos = _categoria(Producto.objects.all(), f, 'categoria_id')
    for pk, codigo, nombre, activo in productos.order_by('nombre', 'pk').values_list('pk', 'codigo', 'nombre', 'activo').iterator():
        grupos[pk] = dict(producto=f'{codigo} · {nombre}' + (' (inactivo)' if not activo else ''), stock=0, costo=None, valor=CERO, activo=activo)
    lotes = _categoria(Lote.objects.all(), f, 'producto__categoria_id')
    for pid, cantidad, costo in lotes.values_list('producto_id', 'cantidad_actual', 'costo_unitario').iterator():
        grupos[pid]['stock'] += cantidad
        grupos[pid]['valor'] += cantidad * costo
    filas = []
    for fila in grupos.values():
        activo = fila.pop('activo')
        if fila['stock']:
            fila['costo'] = (fila['valor'] / fila['stock']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if activo or fila['stock']:
            filas.append(fila)
    return filas, ['Valor calculado por lote; el promedio mostrado está redondeado y no se utiliza para calcular el valor. Incluye existencias vencidas.']


def _ganancias(f):
    grupos = {}
    for pid, codigo, nombre, subtotal in _detalles(f).values_list('presentacion__producto_id', 'presentacion__producto__codigo', 'presentacion__producto__nombre', 'subtotal').iterator():
        fila = grupos.setdefault(pid, dict(producto=f'{codigo} · {nombre}', ventas=CERO, costo=CERO, ganancia=CERO))
        fila['ventas'] += subtotal
    salidas = DetalleVentaLote.objects.filter(detalle_venta__in=_detalles(f))
    for pid, cantidad, costo in salidas.values_list('detalle_venta__presentacion__producto_id', 'cantidad_unidades', 'lote__costo_unitario').iterator():
        grupos[pid]['costo'] += cantidad * costo
    for fila in grupos.values():
        fila['ganancia'] = fila['ventas'] - fila['costo']
    return sorted(grupos.values(), key=lambda x: x['producto']), ['Ganancia bruta de mercadería. No incluye gastos generales ni representa utilidad neta.']


def _vencimientos(f):
    hoy = timezone.localdate(timezone=ZONA)
    consulta = Lote.objects.filter(cantidad_actual__gt=0, fecha_vencimiento__gte=hoy, fecha_vencimiento__lte=hoy + timedelta(days=f['dias']))
    filas = [dict(producto=f'{codigo} · {nombre}', lote=lote, vence=fecha.isoformat(), stock=stock) for codigo, nombre, lote, fecha, stock in consulta.order_by('fecha_vencimiento', 'pk').values_list('producto__codigo', 'producto__nombre', 'codigo_lote', 'fecha_vencimiento', 'cantidad_actual').iterator()]
    return filas, [f'Desde {hoy.isoformat()} hasta {(hoy + timedelta(days=f["dias"])).isoformat()}. Los ya vencidos se consultan en las alertas de inventario.']


def _cierres(f):
    consulta = _rango(Caja.objects.filter(estado='CERRADA'), f, 'fecha_cierre')
    if f.get('usuario'):
        consulta = consulta.filter(usuario=f['usuario'])
    cajas = list(consulta.order_by('fecha_cierre', 'pk').values('pk', 'fecha_cierre', 'turno', 'usuario__username', 'monto_inicial', 'monto_contado'))
    ids = [c['pk'] for c in cajas]
    guardados = {}
    for pk, datos in LogAuditoria.objects.filter(accion='CIERRE_CAJA', entidad='Caja', entidad_id__in=ids).order_by('-fecha', '-pk').values_list('entidad_id', 'valor_nuevo').iterator():
        if pk not in guardados:
            guardados[pk] = datos
    efectivos, movimientos = defaultdict(lambda: CERO), defaultdict(lambda: CERO)
    for pk, monto in Pago.objects.filter(venta__caja_id__in=ids, metodo__es_efectivo=True).values_list('venta__caja_id', 'monto').iterator():
        efectivos[pk] += monto
    for pk, tipo, monto in MovimientoCaja.objects.filter(caja_id__in=ids).values_list('caja_id', 'tipo', 'monto').iterator():
        movimientos[pk] += monto if tipo == 'INGRESO' else -monto
    filas, notas = [], []
    for caja in cajas:
        pk = caja['pk']
        datos = guardados.get(pk)
        resumen = None
        if isinstance(datos, dict) and datos.get('version') == 1 and datos.get('caja_id') == pk:
            try:
                valores = {k: Decimal(datos[k]) for k in ('esperado', 'contado', 'diferencia')}
                if all(v.is_finite() for v in valores.values()) and valores['contado'] - valores['esperado'] == valores['diferencia']:
                    resumen = valores
            except (KeyError, TypeError, ValueError, InvalidOperation):
                pass
        if resumen is None:
            if caja['monto_contado'] is None:
                raise ErrorDeNegocio(f'El turno #{pk} está cerrado sin monto contado; no es posible informar su diferencia.')
            esperado = caja['monto_inicial'] + efectivos[pk] + movimientos[pk]
            resumen = dict(esperado=esperado, contado=caja['monto_contado'], diferencia=caja['monto_contado'] - esperado)
            notas.append(f'Turno #{pk}: importes recalculados; no hay resumen histórico válido.')
        filas.append(dict(fecha=timezone.localtime(caja['fecha_cierre'], ZONA).strftime('%Y-%m-%d %H:%M'), turno=f'#{pk} {caja["turno"]}'.strip(), usuario=caja['usuario__username'], **resumen))
    return filas, notas


CONSULTAS = dict(zip(REPORTES, (_ventas, _metodos, _productos, _compras, _inventario, _ganancias, _vencimientos, _cierres)))


def consultar_reporte(usuario, nombre, filtros):
    """Construye una representación común para HTML, Excel y PDF.

    Pasos:
        1. Autorizar y validar filtros estrictos.
        2. Materializar consultas en una instantánea de lectura.
        3. Preparar totales y gráfico sin consultas adicionales.
    Lanza: PermissionDenied o ErrorDeNegocio por filtros o datos inconsistentes.
    """
    # Paso 1: autorizar antes de consultar información financiera.
    autorizar_reporte(usuario, nombre)
    form = FiltrosReporteForm(nombre, filtros)
    if not form.is_valid():
        raise ErrorDeNegocio(' '.join(str(e) for errores in form.errors.values() for e in errores))
    # Paso 2: no dejar QuerySets diferidos fuera de atomic.
    with transaction.atomic():
        filas, notas = CONSULTAS[nombre](form.cleaned_data)
    # Paso 3: no sumar costos promedio; sí costos vendidos.
    columnas = REPORTES[nombre][2]
    totales = {k: sum((fila[k] for fila in filas), CERO if tipo == 'moneda' else 0)
               for k, _, tipo in columnas if tipo in ('moneda', 'entero') and not (nombre == 'inventario_valorizado' and k == 'costo')}
    grafico = {'etiquetas': [f['periodo'] for f in filas], 'valores': [format(f['total'], '.2f') for f in filas]} if nombre == 'ventas' else None
    etiquetas = {form.fields[k].label or k.replace('_', ' ').capitalize(): str(v) for k, v in form.cleaned_data.items() if v is not None and v != ''}
    return dict(nombre=nombre, titulo=REPORTES[nombre][0], columnas=columnas, filas=filas, totales=totales, grafico=grafico, filtros=etiquetas, notas=notas)


def ventas_agrupadas(desde, hasta, agrupar, *, usuario):
    return consultar_reporte(usuario, 'ventas', dict(desde=desde, hasta=hasta, agrupar=agrupar))


def ganancias(desde, hasta, *, usuario, categoria=None):
    return consultar_reporte(usuario, 'ganancias', dict(desde=desde, hasta=hasta, categoria=categoria))


def inventario_valorizado(*, usuario, categoria=None):
    return consultar_reporte(usuario, 'inventario_valorizado', dict(categoria=categoria))


def compras_por_periodo(desde, hasta, *, usuario, proveedor=None):
    return consultar_reporte(usuario, 'compras', dict(desde=desde, hasta=hasta, proveedor=proveedor))


def productos_mas_vendidos(desde, hasta, *, usuario, categoria=None):
    return consultar_reporte(usuario, 'productos_mas_vendidos', dict(desde=desde, hasta=hasta, categoria=categoria))
