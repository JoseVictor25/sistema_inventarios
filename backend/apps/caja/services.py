"""Caja: consultas autorizadas y escrituras transaccionales idempotentes."""
from decimal import Decimal, InvalidOperation
import hashlib
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Sum

from apps.auditoria.models import LogAuditoria
from apps.core.exceptions import ErrorDeNegocio
from apps.core.operaciones import autorizar
from apps.core.permissions import tiene_permiso
from apps.ventas.models import Pago
from .models import Caja, MovimientoCaja, OperacionCaja
from .forms import AbrirCajaForm, MovimientoCajaForm, CerrarCajaForm
from apps.auditoria.services import registrar_cambio


def _serializar(valor):
    if isinstance(valor, Decimal):
        return format(valor, ".2f")
    if isinstance(valor, dict):
        return {k: _serializar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_serializar(v) for v in valor]
    return valor


def _ejecutar(usuario, accion, datos, formulario, aplicar):
    """Reserva primero el escritor SQLite; reserva y resultado se confirman juntos.

    Un INSERT (no select_for_update) serializa las escrituras SQLite. El índice
    único resuelve reenvíos incluso entre procesos. Un bloqueo agota el timeout
    de conexión y se comunica sin volver a ejecutar la escritura automáticamente.
    """
    autorizar(usuario, "gestionar_caja")
    form = formulario(datos)
    if not form.is_valid():
        raise ErrorDeNegocio(" ".join(str(e) for errores in form.errors.values() for e in errores))
    normalizados = dict(form.cleaned_data)
    clave = normalizados.pop("clave")
    contenido = {"usuario": usuario.pk, "accion": accion, "caja_id": None, **normalizados}
    huella = hashlib.sha256(json.dumps(_serializar(contenido), sort_keys=True,
                                      separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    try:
        with transaction.atomic():
            try:
                with transaction.atomic():
                    operacion = OperacionCaja.objects.create(
                        clave=clave, usuario=usuario, accion=accion, huella=huella)
            except IntegrityError:
                previa = OperacionCaja.objects.filter(clave=clave).first()
                if previa is None:
                    raise
                if (previa.usuario_id, previa.accion, previa.huella) != (usuario.pk, accion, huella):
                    raise ErrorDeNegocio("La clave ya fue utilizada con otros datos. Actualiza el formulario.")
                if accion == "CERRAR" and previa.caja.usuario_id != usuario.pk and not puede_cerrar_ajena(usuario):
                    raise PermissionDenied("Ya no tienes autorización para este cierre ajeno.")
                return previa
            caja, movimiento = aplicar(normalizados)
            operacion.caja = caja
            operacion.movimiento = movimiento
            operacion.full_clean()
            operacion.save(update_fields=["caja", "movimiento"])
            return operacion
    except ValidationError as error:
        raise ErrorDeNegocio(" ".join(error.messages)) from None
    except IntegrityError:
        raise ErrorDeNegocio("La operación entra en conflicto con otro registro. Actualiza la página.") from None
    except OperationalError as error:
        if not any(texto in str(error).lower() for texto in ("locked", "busy")):
            raise
        raise ErrorDeNegocio("Otra operación está en curso. Reintenta con la misma clave y datos.") from None


def _turno_abierto(usuario, caja_id, cierre=False):
    try:
        caja = Caja.objects.select_related("usuario", "cerrada_por").get(pk=caja_id)
    except Caja.DoesNotExist:
        raise ErrorDeNegocio("El turno indicado no existe.") from None
    if caja.usuario_id != usuario.pk and not (cierre and puede_cerrar_ajena(usuario)):
        raise PermissionDenied("Solo puedes operar tu propio turno.")
    if caja.estado != Caja.EstadoCaja.ABIERTA:
        raise ErrorDeNegocio("Este turno está cerrado. Actualiza la página.")
    return caja


def abrir_caja(usuario, monto_inicial, turno="", *, clave):
    """Abre un único turno propio, con reserva idempotente y rollback completo.

    Pasos: autorizar y validar; reservar la clave; comprobar unicidad; guardar.
    Lanza: PermissionDenied por permiso; ErrorDeNegocio por datos o conflicto.
    """
    def aplicar(datos):
        if Caja.objects.filter(usuario=usuario, estado="ABIERTA").exists():
            raise ErrorDeNegocio("Ya tienes una caja abierta.")
        caja = Caja(usuario=usuario, creado_por=usuario, modificado_por=usuario, **datos)
        caja.full_clean()
        caja.save()
        return caja, None
    return _ejecutar(usuario, "ABRIR", dict(clave=clave, monto_inicial=monto_inicial, turno=turno),
                     AbrirCajaForm, aplicar).caja


def registrar_movimiento_caja(usuario, caja_id, tipo, monto, concepto, *, clave):
    """Registra efectivo exclusivamente en el turno explícito abierto del actor.

    Pasos: autorizar y validar; reservar; comprobar propietario/estado; guardar.
    Lanza: PermissionDenied por ámbito; ErrorDeNegocio por turno o datos inválidos.
    """
    def aplicar(datos):
        caja = _turno_abierto(usuario, datos.pop("caja_id"))
        movimiento = MovimientoCaja(caja=caja, usuario=usuario, **datos)
        movimiento.full_clean()
        movimiento.save()
        return caja, movimiento
    return _ejecutar(usuario, "MOVIMIENTO", dict(clave=clave, caja_id=caja_id, tipo=tipo,
                     monto=monto, concepto=concepto), MovimientoCajaForm, aplicar).movimiento


def cerrar_caja(usuario, caja_id, monto_contado, *, clave):
    """Cierra y guarda una instantánea auditable; nunca reabre ni recierra un turno.

    Pasos: autorizar y reservar; comprobar turno; cerrar; auditar; devolver resumen.
    Lanza: PermissionDenied por cierre ajeno; ErrorDeNegocio por datos/conflicto.
    """
    def aplicar(datos):
        caja = _turno_abierto(usuario, datos["caja_id"], cierre=True)
        caja.monto_contado = datos["monto_contado"]
        caja.estado = Caja.EstadoCaja.CERRADA
        caja.fecha_cierre = timezone.now()
        caja.cerrada_por = usuario
        caja.modificado_por = usuario
        caja.full_clean()
        caja.save()
        resumen = _resumen_actual(caja)
        resumen["recalculado"] = False
        registrar_cambio(usuario, "CIERRE_CAJA", "Caja", caja.pk,
                         {"estado": "ABIERTA"}, _serializar(resumen))
        return caja, None
    operacion = _ejecutar(usuario, "CERRAR", dict(clave=clave, caja_id=caja_id,
                         monto_contado=monto_contado), CerrarCajaForm, aplicar)
    return calcular_resumen_caja(operacion.caja, usuario=usuario)

CAMPOS_IMPORTES = ("monto_inicial", "ventas_efectivo", "ingresos", "egresos", "esperado", "contado", "diferencia")


def puede_cerrar_ajena(usuario):
    """La excepción exige Dueño o superusuario activo y gestión de caja."""
    return tiene_permiso(usuario, "gestionar_caja") and (
        usuario.is_superuser or (usuario.rol_id and usuario.rol.nombre == "Dueño"))


def _autorizar_consulta(usuario, caja):
    if caja.usuario_id == usuario.pk and tiene_permiso(usuario, "gestionar_caja"):
        return
    if puede_cerrar_ajena(usuario):
        return
    if caja.estado == Caja.EstadoCaja.CERRADA and tiene_permiso(usuario, "ver_historial_caja"):
        return
    raise PermissionDenied("No tienes permiso para consultar este turno de caja.")


def obtener_caja(usuario, caja_id):
    """Obtiene un turno concreto sin sustituirlo por otro abierto.

    Pasos:
        1. Consultar el turno y su propietario.
        2. Comprobar autorización de consulta.
    Lanza:
        ErrorDeNegocio: turno inexistente.
        PermissionDenied: usuario sin acceso al turno.
    """
    # Paso 1: un ID antiguo nunca se transforma en el ID del siguiente turno.
    try:
        caja = Caja.objects.select_related("usuario", "cerrada_por").get(pk=caja_id)
    except Caja.DoesNotExist:
        raise ErrorDeNegocio("El turno de caja solicitado no existe.") from None
    # Paso 2: permiso más ámbito del objeto.
    _autorizar_consulta(usuario, caja)
    return caja


def _resultado(diferencia):
    if diferencia is None:
        return None
    return "CUADRA" if diferencia == 0 else "SOBRA" if diferencia > 0 else "FALTA"


def _resumen_actual(caja):
    pagos = list(Pago.objects.filter(venta__caja=caja).values(
        "metodo_id", "metodo__nombre", "metodo__es_efectivo").annotate(monto=Sum("monto")).order_by("metodo_id"))
    metodos = [{"id": p["metodo_id"], "nombre": p["metodo__nombre"],
                "es_efectivo": p["metodo__es_efectivo"], "monto": p["monto"]} for p in pagos]
    efectivo = sum((p["monto"] for p in metodos if p["es_efectivo"]), Decimal("0"))
    movimientos = dict(caja.movimientos.values("tipo").annotate(total=Sum("monto")).values_list("tipo", "total"))
    ingresos = movimientos.get(MovimientoCaja.TipoMovimientoCaja.INGRESO, Decimal("0"))
    egresos = movimientos.get(MovimientoCaja.TipoMovimientoCaja.EGRESO, Decimal("0"))
    esperado = caja.monto_inicial + efectivo + ingresos - egresos
    diferencia = caja.monto_contado - esperado if caja.monto_contado is not None else None
    return {
        "version": 1, "caja_id": caja.pk, "propietario_id": caja.usuario_id,
        "propietario": caja.usuario.get_username(), "cerrado_por_id": caja.cerrada_por_id,
        "cerrado_por": caja.cerrada_por.get_username() if caja.cerrada_por_id else None,
        "fecha_apertura": caja.fecha_apertura.isoformat(),
        "fecha_cierre": caja.fecha_cierre.isoformat() if caja.fecha_cierre else None,
        "monto_inicial": caja.monto_inicial, "ventas_efectivo": efectivo,
        "pagos_por_metodo": metodos, "otros_metodos": [p for p in metodos if not p["es_efectivo"]],
        "ingresos": ingresos, "egresos": egresos, "esperado": esperado,
        "contado": caja.monto_contado, "diferencia": diferencia, "resultado": _resultado(diferencia),
        "recalculado": caja.estado == Caja.EstadoCaja.CERRADA,
    }


def _leer_resumen_guardado(caja):
    entrada = LogAuditoria.objects.filter(accion="CIERRE_CAJA", entidad="Caja", entidad_id=caja.pk).order_by("-fecha", "-pk").first()
    if not entrada or not isinstance(entrada.valor_nuevo, dict):
        return None
    datos = entrada.valor_nuevo
    if datos.get("version") != 1 or datos.get("caja_id") != caja.pk:
        return None
    try:
        resumen = dict(datos)
        for campo in CAMPOS_IMPORTES:
            resumen[campo] = Decimal(datos[campo])
            if not resumen[campo].is_finite():
                return None
        resumen["pagos_por_metodo"] = [dict(p, monto=Decimal(p["monto"])) for p in datos["pagos_por_metodo"]]
        if any(not p["monto"].is_finite() for p in resumen["pagos_por_metodo"]):
            return None
        resumen["otros_metodos"] = [p for p in resumen["pagos_por_metodo"] if not p["es_efectivo"]]
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    resumen["resultado"] = _resultado(resumen["diferencia"])
    resumen["recalculado"] = False
    return resumen


def calcular_resumen_caja(caja, *, usuario):
    """Entrega resumen autorizado, conservando la instantánea histórica si existe.

    Pasos:
        1. Releer el turno y comprobar acceso.
        2. Preferir resumen de cierre almacenado; señalar los cierres recalculados.
    Lanza:
        ErrorDeNegocio: turno inexistente.
        PermissionDenied: consulta de turno no autorizada.
    """
    # Paso 1: no confiar en estado ni propietario de una instancia obsoleta.
    actual = obtener_caja(usuario, caja.pk)
    # Paso 2: el cálculo consulta pagos y movimientos por separado, sin duplicar sumas.
    if actual.estado == Caja.EstadoCaja.CERRADA:
        guardado = _leer_resumen_guardado(actual)
        if guardado is not None:
            return guardado
    return _resumen_actual(actual)


def listar_cierres(usuario, pagina=1):
    """Pagina exclusivamente turnos cerrados para el permiso de historial.

    Pasos:
        1. Autorizar consulta global de cierres.
        2. Paginar con orden estable y adjuntar resúmenes autorizados.
    Lanza:
        PermissionDenied: falta ver_historial_caja.
    """
    # Paso 1: gestionar caja propia no equivale a consultar historial global.
    autorizar(usuario, "ver_historial_caja")
    # Paso 2: no incluir turnos abiertos ni permitir modificarlos desde el historial.
    consulta = Caja.objects.filter(estado=Caja.EstadoCaja.CERRADA).select_related("usuario", "cerrada_por").order_by("-fecha_cierre", "-pk")
    pagina_cierres = Paginator(consulta, 20).get_page(pagina)
    for caja in pagina_cierres:
        caja.resumen = calcular_resumen_caja(caja, usuario=usuario)
    return pagina_cierres
