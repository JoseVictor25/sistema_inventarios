"""Ventas: registro transaccional idempotente, FEFO y consultas autorizadas."""
from decimal import Decimal, InvalidOperation
import hashlib
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.caja.models import Caja
from apps.catalogo.models import Presentacion
from apps.core.exceptions import ErrorDeNegocio
from apps.core.operaciones import autorizar
from apps.inventario.models import MovimientoInventario
from apps.inventario.services import descontar_stock_fefo
from .models import DetalleVenta, DetalleVentaLote, MetodoPago, OperacionVenta, Pago, Venta


def _serializar(valor):
    if isinstance(valor, Decimal):
        return format(valor, ".2f")
    if isinstance(valor, dict):
        return {k: _serializar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_serializar(v) for v in valor]
    return valor


def registrar_venta(usuario, lineas, pagos, *, clave):
    """Registra una venta de forma atómica e idempotente (§8.1).

    Pasos:
        1. Autorizar usuario con permiso 'vender'.
        2. Validar que haya al menos una línea y validar formato de cantidades.
        3. Obtener el turno de caja abierto del usuario (RN-10).
        4. Validar que haya al menos un pago y montos positivos.
        5. Calcular huella SHA-256 e insertar reserva de OperacionVenta.
           Si la clave ya existe:
             - Si los datos coinciden: retornar la venta previa ya registrada.
             - Si los datos difieren: rechazar con ErrorDeNegocio.
        6. Re-verificar que la caja siga ABIERTA dentro de la transacción.
        7. Obtener presentaciones activas, calcular subtotales y total (RN-01, RN-08).
           Rechazar venta si total == 0 (D4).
        8. Validar que la suma de pagos coincida exactamente con el total (RN-14).
        9. Crear la Venta y asociarla al turno de caja.
        10. Por cada línea: crear DetalleVenta, descontar existencias por FEFO
            (RN-06, RN-07) y registrar DetalleVentaLote + MovimientoInventario SALIDA.
        11. Registrar los Pagos, enlazar la venta a la OperacionVenta y retornar.

    Lanza:
        PermissionDenied: falta de permiso 'vender'.
        ErrorDeNegocio: validaciones de negocio, stock insuficiente o caja cerrada.
    """
    # Paso 1: autorizar
    autorizar(usuario, "vender")

    # Idempotencia previa: si la venta ya fue confirmada con esta clave, permitir recuperarla
    # incluso si el carrito de la sesión ya se vació tras la confirmación previa.
    previa = OperacionVenta.objects.select_related("venta").filter(clave=clave).first()
    if previa is not None and previa.venta is not None:
        if previa.usuario_id != usuario.pk:
            raise PermissionDenied("La clave pertenece a otro usuario.")
        if not lineas:
            return previa.venta

    # Paso 2: buscar caja abierta del usuario (RN-10)
    caja = Caja.objects.filter(usuario=usuario, estado=Caja.EstadoCaja.ABIERTA).first()
    if not caja:
        raise ErrorDeNegocio("Abre tu turno de caja antes de vender.")

    # Paso 3: validar líneas
    if not lineas or not isinstance(lineas, list):
        raise ErrorDeNegocio("Agrega al menos un producto a la venta.")

    lineas_normalizadas = []
    for l in lineas:
        if not isinstance(l, dict):
            raise ErrorDeNegocio("Formato de línea de venta inválido.")
        pid = l.get("presentacion_id")
        cant = l.get("cantidad")
        if not isinstance(cant, int) or isinstance(cant, bool) or cant < 1:
            raise ErrorDeNegocio("La cantidad debe ser un número entero mayor o igual a 1.")
        lineas_normalizadas.append({"presentacion_id": int(pid), "cantidad": cant})

    lineas_normalizadas.sort(key=lambda x: x["presentacion_id"])

    # Paso 4: validar pagos
    if not pagos or not isinstance(pagos, list):
        raise ErrorDeNegocio("Ingresa al menos un método de pago.")

    pagos_normalizados = []
    metodos_vistos = set()
    for p in pagos:
        if not isinstance(p, dict):
            raise ErrorDeNegocio("Formato de pago inválido.")
        mid = p.get("metodo_id")
        if not mid:
            raise ErrorDeNegocio("Método de pago no especificado.")
        try:
            mid_int = int(mid)
        except (TypeError, ValueError):
            raise ErrorDeNegocio("Identificador de método de pago inválido.")
        if mid_int in metodos_vistos:
            raise ErrorDeNegocio("No se permite duplicar el mismo método de pago en una venta.")
        metodos_vistos.add(mid_int)

        try:
            monto_dec = Decimal(str(p.get("monto", "0")).strip().replace(",", "."))
        except (InvalidOperation, TypeError, ValueError):
            raise ErrorDeNegocio("El monto de pago no es válido.")
        if monto_dec <= Decimal("0.00"):
            raise ErrorDeNegocio("El monto de cada pago debe ser mayor que cero.")

        ref = str(p.get("referencia") or "").strip()
        pagos_normalizados.append({
            "metodo_id": mid_int,
            "monto": format(monto_dec, ".2f"),
            "referencia": ref,
        })

    pagos_normalizados.sort(key=lambda x: (x["metodo_id"], x["monto"], x["referencia"]))

    # Paso 5: calcular huella SHA-256 canónica
    contenido = {
        "usuario_id": usuario.pk,
        "caja_id": caja.pk,
        "lineas": lineas_normalizadas,
        "pagos": pagos_normalizados,
    }
    huella = hashlib.sha256(
        json.dumps(_serializar(contenido), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()

    if previa is not None and previa.venta is not None:
        if previa.huella == huella:
            return previa.venta
        raise ErrorDeNegocio("La clave ya fue utilizada con otros datos. Actualiza la página.")

    try:
        with transaction.atomic():
            # Intentar reservar la clave de idempotencia
            try:
                with transaction.atomic():
                    operacion = OperacionVenta.objects.create(
                        clave=clave,
                        usuario=usuario,
                        huella=huella,
                    )
            except IntegrityError:
                previa = OperacionVenta.objects.select_related("venta").filter(clave=clave).first()
                if previa is None:
                    raise
                if (previa.usuario_id, previa.huella) != (usuario.pk, huella):
                    raise ErrorDeNegocio("La clave ya fue utilizada con otros datos. Actualiza la página.")
                if previa.venta is None:
                    raise ErrorDeNegocio("La venta anterior no se completó. Intenta de nuevo con una nueva clave.")
                return previa.venta

            # Paso 6: asegurar que la caja siga abierta dentro de la transacción
            caja_actual = Caja.objects.select_for_update().filter(pk=caja.pk).first()
            if not caja_actual or caja_actual.estado != Caja.EstadoCaja.ABIERTA:
                raise ErrorDeNegocio("El turno de caja se encuentra cerrado. No se puede registrar la venta.")
            if caja_actual.usuario_id != usuario.pk:
                raise PermissionDenied("Solo puedes registrar ventas en tu propio turno de caja.")

            # Paso 7: cargar y validar presentaciones
            pids = [l["presentacion_id"] for l in lineas_normalizadas]
            pres_map = {
                p.pk: p
                for p in Presentacion.objects.filter(pk__in=pids).select_related("producto")
            }
            if len(pres_map) != len(set(pids)):
                raise ErrorDeNegocio("Una o más presentaciones seleccionadas no existen.")

            lineas_calculadas = []
            total = Decimal("0.00")
            for l in lineas_normalizadas:
                pres = pres_map[l["presentacion_id"]]
                if not pres.activa or not pres.producto.activo:
                    raise ErrorDeNegocio(f"La presentación '{pres.nombre}' de {pres.producto.nombre} no está activa.")

                cant = l["cantidad"]
                precio_aplicado = pres.precio_venta
                unidades = cant * pres.unidades_equivalentes
                subtotal = precio_aplicado * cant

                total += subtotal
                lineas_calculadas.append({
                    "presentacion": pres,
                    "cantidad": cant,
                    "unidades": unidades,
                    "precio_aplicado": precio_aplicado,
                    "subtotal": subtotal,
                })

            # D4: Total == 0 no permitido
            if total <= Decimal("0.00"):
                raise ErrorDeNegocio("El total de la venta no puede ser cero.")

            # Paso 8: verificar métodos y suma de pagos (RN-14)
            metodos_ids = [p["metodo_id"] for p in pagos_normalizados]
            metodos_map = {
                m.pk: m
                for m in MetodoPago.objects.filter(pk__in=metodos_ids, activo=True)
            }
            if len(metodos_map) != len(set(metodos_ids)):
                raise ErrorDeNegocio("Uno o más métodos de pago no existen o no están activos.")

            total_pagos = Decimal("0.00")
            pagos_a_crear = []
            for p in pagos_normalizados:
                metodo = metodos_map[p["metodo_id"]]
                monto_dec = Decimal(p["monto"])
                total_pagos += monto_dec
                pagos_a_crear.append({
                    "metodo": metodo,
                    "monto": monto_dec,
                    "referencia": p["referencia"],
                })

            if total_pagos != total:
                raise ErrorDeNegocio(
                    f"La suma de los pagos ({total_pagos}) no coincide con el total de la venta ({total})."
                )

            # Paso 9: crear la Venta
            venta = Venta(
                caja=caja_actual,
                usuario=usuario,
                total=total,
                creado_por=usuario,
                modificado_por=usuario,
            )
            venta.full_clean()
            venta.save()

            # Paso 10: detalles, descuento FEFO y movimientos
            for lc in lineas_calculadas:
                pres = lc["presentacion"]
                detalle = DetalleVenta(
                    venta=venta,
                    presentacion=pres,
                    cantidad_presentaciones=lc["cantidad"],
                    unidades_totales=lc["unidades"],
                    precio_aplicado=lc["precio_aplicado"],
                    subtotal=lc["subtotal"],
                )
                detalle.full_clean()
                detalle.save()

                # Descontar stock FEFO
                salidas = descontar_stock_fefo(pres.producto, lc["unidades"])
                for lote, cant_unidades in salidas:
                    dvl = DetalleVentaLote(
                        detalle_venta=detalle,
                        lote=lote,
                        cantidad_unidades=cant_unidades,
                    )
                    dvl.full_clean()
                    dvl.save()

                    mov = MovimientoInventario(
                        lote=lote,
                        tipo=MovimientoInventario.TipoMovimiento.SALIDA,
                        cantidad=-cant_unidades,
                        motivo=f"Venta #{venta.pk}",
                        usuario=usuario,
                    )
                    mov.full_clean()
                    mov.save()

            # Paso 11: pagos
            for pc in pagos_a_crear:
                pago = Pago(
                    venta=venta,
                    metodo=pc["metodo"],
                    monto=pc["monto"],
                    referencia=pc["referencia"],
                )
                pago.full_clean()
                pago.save()

            operacion.venta = venta
            operacion.save(update_fields=["venta"])
            return venta

    except ValidationError as error:
        raise ErrorDeNegocio(" ".join(error.messages)) from None
    except IntegrityError:
        raise ErrorDeNegocio("La operación entra en conflicto con otro registro. Actualiza la página.") from None
    except OperationalError as error:
        if not any(texto in str(error).lower() for texto in ("locked", "busy")):
            raise
        raise ErrorDeNegocio("Otra operación está en curso. Reintenta con la misma clave y datos.") from None


def obtener_venta(usuario, venta_id):
    """Obtiene el detalle inmutable de una venta autorizada.

    Pasos:
        1. Autorizar permiso 'vender'.
        2. Consultar venta con detalles, presentaciones, productos, lotes y pagos.
    Lanza:
        PermissionDenied si no tiene permiso.
        ErrorDeNegocio si no existe la venta.
    """
    autorizar(usuario, "vender")
    try:
        return (
            Venta.objects.select_related("caja", "usuario")
            .prefetch_related(
                "detalles__presentacion__producto",
                "detalles__salidas_lote__lote",
                "pagos__metodo",
            )
            .get(pk=venta_id)
        )
    except Venta.DoesNotExist:
        raise ErrorDeNegocio("La venta solicitada no existe.") from None


def listar_ventas_del_dia(usuario, fecha=None, pagina=1):
    """Lista las ventas del día paginadas y calcula el total del día (§9.6).

    Pasos:
        1. Autorizar permiso 'vender'.
        2. Filtrar ventas por fecha (por defecto fecha actual).
        3. Calcular total del día.
        4. Paginar resultados (20 por página).
    """
    autorizar(usuario, "vender")
    if fecha is None:
        fecha = timezone.localdate()

    ventas_qs = (
        Venta.objects.filter(fecha__date=fecha)
        .select_related("caja", "usuario")
        .prefetch_related("pagos__metodo", "detalles")
        .order_by("-fecha", "-pk")
    )
    total_dia = ventas_qs.aggregate(total=Sum("total"))["total"] or Decimal("0.00")
    paginador = Paginator(ventas_qs, 20)
    pagina_obj = paginador.get_page(pagina)
    return pagina_obj, total_dia
