"""Pantallas del módulo de compras y proveedores — Fase 4.

Controla autorización de vistas con @permiso_requerido("gestionar_compras")
y delega las escrituras a los servicios de negocio correspondientes.
"""
import threading
import uuid

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.catalogo.models import Producto
from apps.core.exceptions import ErrorDeNegocio
from apps.core.permissions import permiso_requerido
from . import services
from .forms import CompraCabeceraForm, FiltroComprasForm, ProveedorForm, extraer_lineas_post
from .models import Compra, Proveedor

# Bloqueo atómico en memoria para prevenir solicitudes concurrentes con el mismo token
_tokens_en_proceso = set()
_lock_tokens = threading.Lock()


# --- Proveedores (heredado de Fase 3) ----------------------------------------

@permiso_requerido("gestionar_compras")
@require_GET
def proveedor_lista(request):
    return render(
        request,
        "compras/proveedor_lista.html",
        {"proveedores": Proveedor.objects.all()},
    )


@permiso_requerido("gestionar_compras")
@require_http_methods(["GET", "POST"])
def proveedor_form(request, pk=None):
    proveedor = get_object_or_404(Proveedor, pk=pk) if pk else None
    form = ProveedorForm(request.POST if request.method == "POST" else None, instance=proveedor)
    if request.method == "POST" and form.is_valid():
        try:
            services.guardar_proveedor(
                request.user,
                {c: form.cleaned_data[c] for c in services.CAMPOS_PROVEEDOR},
                pk,
            )
        except ErrorDeNegocio as error:
            form.add_error(None, error.mensaje)
        else:
            messages.success(request, "Proveedor guardado correctamente.")
            return redirect("compras:proveedor_lista")
    return render(
        request,
        "compras/proveedor_form.html",
        {"form": form, "editando": pk is not None},
    )


# --- Compras (Fase 4) --------------------------------------------------------

@permiso_requerido("gestionar_compras")
@require_GET
def compra_lista(request):
    """Muestra el historial de compras con filtros de fecha y paginación."""
    filtro_form = FiltroComprasForm(request.GET)
    desde = None
    hasta = None
    if filtro_form.is_valid():
        desde = filtro_form.cleaned_data.get("desde")
        hasta = filtro_form.cleaned_data.get("hasta")

    page_num = request.GET.get("page", 1)
    page_obj, total_filtrado = services.listar_compras(
        request.user,
        desde=desde,
        hasta=hasta,
        pagina=page_num,
    )

    filtros = request.GET.copy()
    filtros.pop("page", None)

    context = {
        "page_obj": page_obj,
        "desde": desde.isoformat() if desde else "",
        "hasta": hasta.isoformat() if hasta else "",
        "total_filtrado": total_filtrado,
        "filtros_query": filtros.urlencode(),
        "form_filtro": filtro_form,
    }
    return render(request, "compras/compra_lista.html", context)


@permiso_requerido("gestionar_compras")
@require_http_methods(["GET", "POST"])
def compra_crear(request):
    """Formulario y procesamiento de registro de una nueva compra."""
    if request.method == "GET":
        token = uuid.uuid4().hex
        request.session["compra_token"] = token
        form = CompraCabeceraForm()
        proveedores = Proveedor.objects.filter(activo=True).order_by("nombre")
        productos = Producto.objects.filter(activo=True).order_by("nombre")
        context = {
            "form": form,
            "proveedores": proveedores,
            "productos": productos,
            "compra_token": token,
        }
        return render(request, "compras/compra_form.html", context)

    # POST: Validar token de idempotencia contra envíos duplicados
    token = request.POST.get("token_idempotencia")
    token_esperado = request.session.get("compra_token")
    if not token or token != token_esperado:
        messages.warning(
            request,
            "Esta solicitud de compra ya fue procesada o el formulario expiró.",
        )
        return redirect("compras:compra_lista")

    # Exclusión mutua atómica para solicitudes concurrentes simultáneas
    with _lock_tokens:
        if token in _tokens_en_proceso:
            messages.warning(
                request,
                "Esta solicitud de compra ya está siendo procesada. Por favor espera.",
            )
            return redirect("compras:compra_lista")
        _tokens_en_proceso.add(token)

    try:
        form = CompraCabeceraForm(request.POST)
        lineas = extraer_lineas_post(request.POST)

        if not lineas:
            form.add_error(None, "Debes agregar al menos un producto a la compra.")

        if form.is_valid() and lineas:
            try:
                compra = services.registrar_compra(
                    usuario=request.user,
                    proveedor=form.cleaned_data["proveedor"],
                    lineas=lineas,
                    observacion=form.cleaned_data.get("observacion", ""),
                    fecha=form.cleaned_data.get("fecha"),
                )
            except ErrorDeNegocio as error:
                form.add_error(None, error.mensaje)
            else:
                # Consumir el token de sesión tras registro exitoso
                request.session.pop("compra_token", None)
                messages.success(request, f"Compra #{compra.pk} registrada exitosamente.")
                return redirect("compras:compra_detalle", pk=compra.pk)

        # Si hay error de validación, regenerar token para permitir corregir y reenviar
        nuevo_token = uuid.uuid4().hex
        request.session["compra_token"] = nuevo_token

        status_code = 422 if request.headers.get("HX-Request") else 200
        context = {
            "form": form,
            "proveedores": Proveedor.objects.filter(activo=True).order_by("nombre"),
            "productos": Producto.objects.filter(activo=True).order_by("nombre"),
            "compra_token": nuevo_token,
        }
        return render(request, "compras/compra_form.html", context, status=status_code)
    finally:
        with _lock_tokens:
            _tokens_en_proceso.discard(token)


@permiso_requerido("gestionar_compras")
@require_GET
def compra_linea(request):
    """Endpoint HTMX: entrega un fragmento de fila para agregar un producto."""
    indice = request.GET.get("indice", "0")
    productos = Producto.objects.filter(activo=True).order_by("nombre")
    context = {
        "indice": indice,
        "productos": productos,
    }
    return render(request, "compras/partials/_linea_compra.html", context)


@permiso_requerido("gestionar_compras")
@require_GET
def compra_detalle(request, pk):
    """Detalle de una compra con sus líneas, lotes y movimientos asociados."""
    try:
        compra = services.obtener_compra(request.user, pk)
    except ErrorDeNegocio:
        raise Http404("La compra solicitada no existe.")

    detalles = compra.detalles.select_related("producto", "lote").all()
    lotes = [d.lote for d in detalles if hasattr(d, "lote")]

    context = {
        "compra": compra,
        "detalles": detalles,
        "lotes": lotes,
    }
    return render(request, "compras/compra_detalle.html", context)
