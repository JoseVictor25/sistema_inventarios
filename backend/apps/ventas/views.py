"""Vistas de ventas: POS, carrito HTMX, confirmación y consulta inmutable."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.caja.models import Caja
from apps.catalogo.models import Producto
from apps.core.exceptions import ErrorDeNegocio
from apps.core.permissions import permiso_requerido
from .carrito import (
    agregar_linea,
    cambiar_cantidad,
    cambiar_presentacion,
    enriquecer_carrito,
    obtener_carrito,
    quitar_linea,
    vaciar_carrito,
)
from .forms import leer_pagos, FiltroVentasForm
from .models import MetodoPago
from .services import listar_ventas_del_dia, listar_ventas, obtener_venta, registrar_venta


def _preparar_productos(consulta):
    """Agrega stock_actual, presentaciones activas y marcas de alerta a cada producto."""
    productos = list(
        consulta.select_related("categoria")
        .prefetch_related("presentaciones", "lotes")
    )
    hoy = timezone.localdate()
    dias_alerta = getattr(settings, "DIAS_ALERTA_VENCIMIENTO", 30)
    limite_vencimiento = hoy + timedelta(days=dias_alerta)

    for p in productos:
        # Presentaciones activas (D3: la primera es la predeterminada)
        p.presentaciones_activas = [pres for pres in p.presentaciones.all() if pres.activa]
        p.presentacion_defecto = p.presentaciones_activas[0] if p.presentaciones_activas else None
        # Stock actual en unidades
        stock = p.stock_actual
        p.stock_total = stock
        # Alertas visibles
        p.sin_stock = stock <= 0
        p.stock_bajo = 0 < stock <= p.stock_minimo
        # Vence pronto si algún lote con stock vence dentro del umbral de alerta
        p.vence_pronto = any(
            lote.cantidad_actual > 0
            and lote.fecha_vencimiento
            and hoy <= lote.fecha_vencimiento <= limite_vencimiento
            for lote in p.lotes.all()
        )
    return productos


@login_required
@permiso_requerido("vender")
@require_GET
def pos(request):
    """Pantalla principal de venta (POS) (§9.6, §9.11)."""
    caja = Caja.objects.filter(usuario=request.user, estado=Caja.EstadoCaja.ABIERTA).first()
    carrito = enriquecer_carrito(request.session)
    metodos_pago = MetodoPago.objects.filter(activo=True)

    # Catálogo inicial (primeros 30 productos activos)
    productos = _preparar_productos(
        Producto.objects.filter(activo=True).order_by("nombre")[:30]
    )

    contexto = {
        "caja": caja,
        "carrito": carrito,
        "metodos_pago": metodos_pago,
        "productos": productos,
    }
    return render(request, "ventas/pos.html", contexto)


@login_required
@permiso_requerido("vender")
@require_GET
def buscar(request):
    """Buscador reactivo de productos para la columna izquierda del POS."""
    q = request.GET.get("q", "").strip()
    consulta = Producto.objects.filter(activo=True)
    if q:
        consulta = consulta.filter(
            Q(nombre__icontains=q) | Q(codigo__icontains=q) | Q(categoria__nombre__icontains=q)
        )
    productos = _preparar_productos(consulta.order_by("nombre")[:40])
    return render(request, "ventas/partials/_lista_productos.html", {"productos": productos, "q": q})


@login_required
@permiso_requerido("vender")
def _contexto_carrito(request, carrito, metodos_pago, error=None):
    """Genera el contexto para el fragmento _carrito.html asegurando el estado de caja del usuario."""
    caja = Caja.objects.filter(usuario=request.user, estado=Caja.EstadoCaja.ABIERTA).first()
    ctx = {
        "carrito": carrito,
        "metodos_pago": metodos_pago,
        "caja": caja,
    }
    if error:
        ctx["error"] = error
    return ctx


@login_required
@permiso_requerido("vender")
@require_POST
def carrito_agregar(request):
    """Agrega una presentación al carrito de la sesión."""
    presentacion_id = request.POST.get("presentacion_id")
    cantidad = request.POST.get("cantidad", 1)
    metodos_pago = MetodoPago.objects.filter(activo=True)

    try:
        try:
            pid = int(presentacion_id)
            cant = int(cantidad)
        except (ValueError, TypeError):
            raise ErrorDeNegocio("Presentación o cantidad inválida.")
        agregar_linea(request.session, pid, cant)
        carrito = enriquecer_carrito(request.session)
        return render(request, "ventas/partials/_carrito.html", _contexto_carrito(request, carrito, metodos_pago))
    except ErrorDeNegocio as error:
        carrito = enriquecer_carrito(request.session)
        return render(
            request,
            "ventas/partials/_carrito.html",
            _contexto_carrito(request, carrito, metodos_pago, error=error.mensaje),
            status=422,
        )


@login_required
@permiso_requerido("vender")
@require_POST
def carrito_actualizar(request):
    """Actualiza la cantidad o la presentación de una línea del carrito."""
    metodos_pago = MetodoPago.objects.filter(activo=True)
    try:
        try:
            indice = int(request.POST.get("indice", -1))
        except (ValueError, TypeError):
            raise ErrorDeNegocio("Índice de línea inválido.")

        if "cantidad" in request.POST:
            try:
                cantidad = int(request.POST.get("cantidad", 1))
            except (ValueError, TypeError):
                raise ErrorDeNegocio("Cantidad inválida.")
            cambiar_cantidad(request.session, indice, cantidad)

        if "presentacion_id" in request.POST:
            try:
                presentacion_id = int(request.POST.get("presentacion_id"))
            except (ValueError, TypeError):
                raise ErrorDeNegocio("Presentación inválida.")
            cambiar_presentacion(request.session, indice, presentacion_id)

        carrito = enriquecer_carrito(request.session)
        return render(request, "ventas/partials/_carrito.html", _contexto_carrito(request, carrito, metodos_pago))
    except ErrorDeNegocio as error:
        carrito = enriquecer_carrito(request.session)
        return render(
            request,
            "ventas/partials/_carrito.html",
            _contexto_carrito(request, carrito, metodos_pago, error=error.mensaje),
            status=422,
        )


@login_required
@permiso_requerido("vender")
@require_POST
def carrito_quitar(request):
    """Quita una línea del carrito de compras."""
    metodos_pago = MetodoPago.objects.filter(activo=True)
    try:
        try:
            indice = int(request.POST.get("indice", -1))
        except (ValueError, TypeError):
            raise ErrorDeNegocio("Índice de línea inválido.")
        quitar_linea(request.session, indice)
        carrito = enriquecer_carrito(request.session)
        return render(request, "ventas/partials/_carrito.html", _contexto_carrito(request, carrito, metodos_pago))
    except ErrorDeNegocio as error:
        carrito = enriquecer_carrito(request.session)
        return render(
            request,
            "ventas/partials/_carrito.html",
            _contexto_carrito(request, carrito, metodos_pago, error=error.mensaje),
            status=422,
        )


@login_required
@permiso_requerido("vender")
@require_POST
def carrito_vaciar(request):
    """Vacía todas las líneas del carrito."""
    vaciar_carrito(request.session)
    carrito = enriquecer_carrito(request.session)
    metodos_pago = MetodoPago.objects.filter(activo=True)
    return render(request, "ventas/partials/_carrito.html", _contexto_carrito(request, carrito, metodos_pago))


@login_required
@permiso_requerido("vender")
@require_POST
def confirmar(request):
    """Confirma la venta del carrito (200 éxito o 422 con error en _carrito.html)."""
    carrito_crudo = obtener_carrito(request.session)
    carrito_enriquecido = enriquecer_carrito(request.session)
    metodos_pago = MetodoPago.objects.filter(activo=True)

    clave = request.POST.get("clave") or carrito_crudo.get("clave")

    try:
        pagos = leer_pagos(request.POST, total_venta=carrito_enriquecido["total"])
        if MetodoPago.objects.filter(pk__in=[p['metodo_id'] for p in pagos], nombre__iexact='QR').exists() and request.POST.get('qr_confirmado') != 'si':
            raise ErrorDeNegocio('Confirma manualmente que recibiste el pago QR antes de finalizar.')
        venta = registrar_venta(
            usuario=request.user,
            lineas=carrito_crudo.get("lineas", []),
            pagos=pagos,
            clave=clave,
        )
    except ErrorDeNegocio as error:
        return render(
            request,
            "ventas/partials/_carrito.html",
            _contexto_carrito(request, carrito_enriquecido, metodos_pago, error=error.mensaje),
            status=422,
        )

    vaciar_carrito(request.session)
    from .impresion import leer, DEFAULT
    from django.core.exceptions import ValidationError
    try:
        configuracion = leer()
        ofrecer = configuracion['ofrecer_al_finalizar']
        escpos_listo = configuracion['metodo'] == 'ESC/POS' and configuracion['escpos_confirmado']
    except (ValidationError, OSError):
        ofrecer = DEFAULT['ofrecer_al_finalizar']
        escpos_listo = False
    from uuid import uuid4
    return render(request, "ventas/partials/_venta_confirmada.html",
                  {"venta": venta, "ofrecer_comprobante": ofrecer, "escpos_listo": escpos_listo,
                   "intento_impresion": uuid4().hex})


@login_required
@permiso_requerido("vender")
@require_GET
def lista(request):
    """Historial de ventas con filtros y paginación."""
    from urllib.parse import urlencode
    filtros = FiltroVentasForm(request.GET)
    if not filtros.is_valid():
        return render(request, 'ventas/venta_lista.html', {'filtros': filtros}, status=422)
    datos = filtros.cleaned_data
    desde = datos.get('desde') or timezone.localdate()
    hasta = datos.get('hasta') or timezone.localdate()
    vendedor = datos.get('vendedor')
    page_obj, total_dia = listar_ventas(request.user, desde, hasta,
                                        vendedor.pk if vendedor else None, request.GET.get('page', 1))
    filtros_query = urlencode({k: v for k, v in request.GET.items() if k != 'page' and v})
    return render(
        request,
        "ventas/venta_lista.html",
        {"page_obj": page_obj, "total_dia": total_dia, 'filtros': filtros,
         'filtros_query': filtros_query, 'desde': desde, 'hasta': hasta,
         'filtros_activos': bool(filtros_query)},
    )


@login_required
@permiso_requerido("vender")
@require_GET
def detalle(request, pk):
    """Detalle inmutable de una venta registrada (§9.6)."""
    venta = obtener_venta(request.user, pk)
    return render(
        request,
        "ventas/venta_detalle.html",
        {
            "venta": venta,
            "detalles": venta.detalles.all(),
            "pagos": venta.pagos.all(),
        },
    )


@login_required
@permiso_requerido("vender")
@require_GET
def comprobante(request, pk):
    from uuid import uuid4
    from .impresion import leer
    from django.http import Http404
    try:
        venta = obtener_venta(request.user, pk)
    except ErrorDeNegocio:
        raise Http404('Venta no encontrada.') from None
    from .ticket import desde_venta, renderizar, medidas_pagina
    configuracion = leer()
    ticket = desde_venta(venta, configuracion['mensaje'])
    _, meta = renderizar(ticket, configuracion)
    return render(request, "ventas/venta_comprobante.html", {
        "venta": venta, "detalles": venta.detalles.all(), "pagos": venta.pagos.all(),
        "impresion": configuracion,
        "ticket": ticket,
        "pagina": medidas_pagina(meta, configuracion),
        "escpos_listo": configuracion['metodo'] == 'ESC/POS' and configuracion['escpos_confirmado'],
        "intento_impresion": uuid4().hex,
    })


def _ticket_autorizado(request, pk):
    from .impresion import leer
    from .ticket import desde_venta
    from django.http import Http404
    try:
        venta = obtener_venta(request.user, pk)
    except ErrorDeNegocio:
        raise Http404('Venta no encontrada.') from None
    configuracion = leer()
    return desde_venta(venta, configuracion['mensaje']), configuracion


@login_required
@permiso_requerido('vender')
@require_GET
def imagen_comprobante(request, pk):
    from django.http import HttpResponse
    from .ticket import png
    ticket, configuracion = _ticket_autorizado(request, pk)
    datos, _ = png(ticket, configuracion)
    respuesta = HttpResponse(datos, content_type='image/png')
    respuesta['Cache-Control'] = 'private, no-store'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@login_required
@permiso_requerido('vender')
@require_GET
def pdf_comprobante(request, pk):
    from django.http import HttpResponse
    from .ticket import pdf
    ticket, configuracion = _ticket_autorizado(request, pk)
    try:
        datos, _ = pdf(ticket, configuracion)
    except ValueError:
        return HttpResponse('El ticket excede una página PDF.', status=422)
    respuesta = HttpResponse(datos, content_type='application/pdf')
    respuesta['Content-Disposition'] = f'inline; filename="comprobante_{pk}.pdf"'
    respuesta['Cache-Control'] = 'private, no-store'
    return respuesta


@login_required
@permiso_requerido('vender')
@require_POST
def imprimir_escpos(request, pk):
    import logging
    from uuid import UUID
    from django.core.cache import cache
    from django.http import HttpResponse
    from .ticket import renderizar
    from .escpos import bytes_raster, enviar_cola, listar_colas
    from .impresion import avance_final
    ticket, configuracion = _ticket_autorizado(request, pk)
    if configuracion['metodo'] != 'ESC/POS' or not configuracion['escpos_confirmado']:
        return HttpResponse('ESC/POS no está habilitado.', status=403)
    try:
        intento = UUID(request.POST.get('intento_impresion', ''))
        if intento.version != 4:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        return HttpResponse('Falta el identificador del intento de impresión.', status=400)
    clave = f'escpos:{pk}:{intento.hex}'
    if not cache.add(clave, True, timeout=600):
        return HttpResponse('Este ticket ya fue enviado a la cola.', status=409)
    try:
        if configuracion['impresora'] not in listar_colas():
            cache.delete(clave)
            return HttpResponse('La cola configurada no está disponible.', status=503)
        # El raster enviado se recorta; el avance físico es independiente.
        imagen, _ = renderizar(ticket, {**configuracion, 'margen_inferior_mm': 0})
        datos = bytes_raster(imagen, avance_final_mm=avance_final(configuracion),
                             margen_superior_mm=configuracion['margen_superior_mm'], recortar=True,
                             ancho_mm=configuracion['ancho'],
                             cortar=configuracion['corte_automatico'])
        trabajo = enviar_cola(configuracion['impresora'], datos)
    except (OSError, ValueError, RuntimeError):
        logging.getLogger(__name__).exception('No se pudo enviar el comprobante a la cola ESC/POS')
        return HttpResponse('No se pudo enviar el trabajo a la cola.', status=503)
    logging.getLogger(__name__).info('Comprobante de venta %s aceptado por spooler, trabajo %s', pk, trabajo)
    return HttpResponse(f'Trabajo {trabajo} aceptado por la cola. Verifique la impresión física.')


@login_required
@permiso_requerido('gestionar_usuarios')
@require_POST
def imprimir_calibracion(request):
    """Una regla de 0 a 40 mm, enviada con el mismo cierre que un ticket."""
    import logging
    from uuid import UUID
    from django.core.cache import cache
    from django.http import HttpResponse
    from .impresion import leer, avance_final
    from .escpos import bytes_raster, enviar_cola, imagen_calibracion, listar_colas
    configuracion = leer()
    if configuracion['metodo'] != 'ESC/POS' or not configuracion['escpos_confirmado']:
        return HttpResponse('ESC/POS no está habilitado.', status=403)
    try:
        intento = UUID(request.POST.get('intento_impresion', ''))
        if intento.version != 4:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        return HttpResponse('Falta el identificador del intento de impresión.', status=400)
    clave = f'escpos:calibracion:{intento.hex}'
    if not cache.add(clave, True, timeout=600):
        return HttpResponse('Esta calibración ya fue enviada a la cola.', status=409)
    try:
        if configuracion['impresora'] not in listar_colas():
            cache.delete(clave)
            return HttpResponse('La cola configurada no está disponible.', status=503)
        imagen = imagen_calibracion(configuracion['ancho'])
        datos = bytes_raster(imagen, avance_final_mm=avance_final(configuracion),
                             margen_superior_mm=configuracion['margen_superior_mm'],
                             ancho_mm=configuracion['ancho'],
                             cortar=configuracion['corte_automatico'], recortar=True)
        trabajo = enviar_cola(configuracion['impresora'], datos)
    except (OSError, ValueError, RuntimeError):
        logging.getLogger(__name__).exception('No se pudo enviar la calibración ESC/POS')
        return HttpResponse('No se pudo enviar la calibración a la cola.', status=503)
    return HttpResponse(f'Calibración {trabajo} aceptada por la cola.')


@login_required
@permiso_requerido("gestionar_usuarios")
@require_http_methods(["GET", "POST"])
def configurar_impresion(request):
    from uuid import uuid4
    from .impresion import leer, guardar
    from django.core.exceptions import ValidationError
    from django.shortcuts import redirect
    from .escpos import listar_colas
    error = None
    if request.method == 'POST':
        try:
            metodo = request.POST.get('metodo', 'Windows')
            nombre = request.POST.get('impresora', '').strip()
            if metodo == 'ESC/POS' and nombre not in listar_colas():
                raise ValidationError('Selecciona una cola Windows instalada.')
            guardar({'ancho': int(request.POST.get('ancho', 0)), 'metodo': metodo,
                     'impresora': nombre,
                     'escpos_confirmado': request.POST.get('escpos_confirmado') == 'on',
                     'corte_automatico': request.POST.get('corte_automatico') == 'on',
                     'alimentar_lineas': int(request.POST.get('alimentar_lineas', 2)),
                     'avance_final_mm': (None if request.POST.get('avance_final_mm', '').strip() == ''
                                         else int(request.POST['avance_final_mm'])),
                     'columnas_80': int(request.POST.get('columnas_80', 48)),
                     'columnas_58': int(request.POST.get('columnas_58', 32)),
                     'margen_superior_mm': int(request.POST.get('margen_superior_mm', 2)),
                     'margen_inferior_mm': int(request.POST.get('margen_inferior_mm', 5)),
                     'vista_previa': request.POST.get('vista_previa') == 'on',
                     'ofrecer_al_finalizar': request.POST.get('ofrecer_al_finalizar') == 'on',
                     'impresion_manual': request.POST.get('impresion_manual') == 'on',
                     'mensaje': request.POST.get('mensaje', '')})
            from django.contrib import messages
            messages.success(request, 'Configuración de impresión guardada correctamente.')
            return redirect('ventas:configurar_impresion')
        except (ValidationError, ValueError, OSError) as exc:
            error = str(exc)
    try:
        colas = listar_colas()
    except OSError:
        colas = []
    return render(request, 'ventas/configurar_impresion.html',
                  {'impresion': leer(), 'error': error, 'colas': colas,
                   'intento_calibracion': uuid4().hex}, status=422 if error else 200)
