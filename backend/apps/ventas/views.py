"""Vistas de ventas: POS, carrito HTMX, confirmación y consulta inmutable."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

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
from .forms import leer_pagos
from .models import MetodoPago
from .services import listar_ventas_del_dia, obtener_venta, registrar_venta


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
    return render(request, "ventas/partials/_venta_confirmada.html", {"venta": venta})


@login_required
@permiso_requerido("vender")
@require_GET
def lista(request):
    """Historial de ventas del día actual con totales y paginación (§9.6)."""
    pagina = request.GET.get("page", 1)
    page_obj, total_dia = listar_ventas_del_dia(request.user, pagina=pagina)
    return render(
        request,
        "ventas/venta_lista.html",
        {"page_obj": page_obj, "total_dia": total_dia},
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
