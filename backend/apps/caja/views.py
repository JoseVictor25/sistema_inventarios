"""Pantallas de turnos; las escrituras se delegan en servicios autorizados."""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from apps.core.exceptions import ErrorDeNegocio
from apps.core.permissions import permiso_requerido
from . import services
from .forms import AbrirCajaForm, MovimientoCajaForm, CerrarCajaForm
from .models import Caja


def _contexto(request, caja=None, **formularios):
    contexto = {
        "caja": caja,
        "form_abrir": AbrirCajaForm(auto_id="abrir_%s"),
        "form_movimiento": MovimientoCajaForm(initial={"caja_id": caja.pk if caja else None}, auto_id="mov_%s"),
        "form_cerrar": CerrarCajaForm(initial={"caja_id": caja.pk if caja else None}, auto_id="cerrar_%s"),
        "cajas_abiertas": Caja.objects.filter(estado="ABIERTA").select_related("usuario")
                          if services.puede_cerrar_ajena(request.user) else [],
    }
    if caja:
        contexto.update(resumen=services.calcular_resumen_caja(caja, usuario=request.user),
                        movimientos=caja.movimientos.select_related("usuario"),
                        propia=caja.usuario_id == request.user.pk)
    contexto.update(formularios)
    return contexto


@permiso_requerido("gestionar_caja")
@require_GET
def estado(request):
    if request.GET.get("caja_id"):
        try:
            caja = services.obtener_caja(request.user, int(request.GET["caja_id"]))
        except (ValueError, ErrorDeNegocio):
            raise Http404("El turno no existe.") from None
    else:
        caja = Caja.objects.filter(usuario=request.user, estado="ABIERTA").first()
    return render(request, "caja/estado.html", _contexto(request, caja))


def _guardar(request, clase, nombre, funcion):
    form = clase(request.POST, auto_id={"form_abrir": "abrir_%s", "form_movimiento": "mov_%s", "form_cerrar": "cerrar_%s"}[nombre])
    caja = None
    if form.is_valid():
        try:
            resultado = funcion(request.user, **form.cleaned_data)
        except ErrorDeNegocio as error:
            form.add_error(None, error.mensaje)
        else:
            if nombre == "form_movimiento":
                caja = resultado.caja
                if request.headers.get("HX-Request"):
                    return render(request, "caja/partials/_actualizacion.html", _contexto(request, caja))
            elif nombre == "form_cerrar":
                caja = services.obtener_caja(request.user, resultado["caja_id"])
                return render(request, "caja/cierre.html", _contexto(request, caja))
            else:
                caja = resultado
            messages.success(request, "Operación de caja registrada correctamente.")
            return redirect(f"/caja/?caja_id={caja.pk}")
    # Un POST antiguo nunca toma automáticamente el turno nuevo del usuario.
    identificador = form.cleaned_data.get("caja_id")
    if identificador:
        try:
            caja = services.obtener_caja(request.user, identificador)
        except ErrorDeNegocio:
            pass
    contexto = _contexto(request, caja, **{nombre: form}, error_operacion=form.errors)
    plantilla = "caja/partials/_actualizacion.html" if nombre == "form_movimiento" and request.headers.get("HX-Request") else "caja/estado.html"
    return render(request, plantilla, contexto, status=422)


@permiso_requerido("gestionar_caja")
@require_POST
def abrir(request):
    return _guardar(request, AbrirCajaForm, "form_abrir", services.abrir_caja)


@permiso_requerido("gestionar_caja")
@require_POST
def movimiento_crear(request):
    return _guardar(request, MovimientoCajaForm, "form_movimiento", services.registrar_movimiento_caja)


@permiso_requerido("gestionar_caja")
@require_POST
def cerrar(request):
    return _guardar(request, CerrarCajaForm, "form_cerrar", services.cerrar_caja)


@permiso_requerido("ver_historial_caja")
@require_GET
def historial(request):
    return render(request, "caja/historial.html", {
        "page_obj": services.listar_cierres(request.user, request.GET.get("page", 1)),
    })
