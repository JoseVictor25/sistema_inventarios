"""Servicios de compras y gestión de proveedores — Fase 4.

Implementa RN-01, RN-05, RN-07, RN-17, RN-19, RN-20 y RN-21.
"""
import datetime
from decimal import Decimal, InvalidOperation
import re

from django.core.paginator import Paginator
from django.db.models import Sum
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.core.exceptions import ErrorDeNegocio
from apps.core.operaciones import asignar_campos, autorizar, operacion
from apps.core.utils import asignar_auditoria
from apps.core.validators import validar_dinero
from apps.inventario.models import Lote, MovimientoInventario
from .models import Compra, DetalleCompra, Proveedor

CAMPOS_PROVEEDOR = ("nombre", "tipo", "contacto", "telefono", "origen", "activo")


@operacion("gestionar_compras")
def guardar_proveedor(usuario, datos, proveedor_id=None):
    """Crea o edita datos comerciales, sin borrar compras.

    Pasos:
        1. Recuperar proveedor y asignar campos permitidos.
        2. Validar, asignar autoría y guardar.
    Lanza:
        ErrorDeNegocio: nombre duplicado, tipo inválido o registro inexistente.
    """
    # Paso 1: no se aceptan campos de auditoría desde el cliente.
    proveedor = Proveedor.objects.get(pk=proveedor_id) if proveedor_id else Proveedor()
    asignar_campos(proveedor, datos, CAMPOS_PROVEEDOR)
    # Paso 2: la transacción del decorador mantiene el registro intacto si falla.
    asignar_auditoria(proveedor, usuario)
    proveedor.full_clean()
    proveedor.save()
    return proveedor


def _extraer_numero_lote(codigo, anio):
    """Extrae el número correlativo de un código de lote con formato L-AAAA-NNNN."""
    match = re.match(rf"^L-{anio}-(\d+)$", str(codigo))
    return int(match.group(1)) if match else 0


def _siguiente_numero_lote(anio):
    """Obtiene el siguiente número correlativo disponible para el año indicado."""
    prefix = f"L-{anio}-"
    codigos = list(
        Lote.objects.select_for_update()
        .filter(codigo_lote__startswith=prefix)
        .values_list("codigo_lote", flat=True)
    )
    max_num = max([_extraer_numero_lote(c, anio) for c in codigos], default=0)
    return max_num + 1


def generar_codigo_lote(anio=None):
    """Genera un código de lote correlativo no utilizado en formato L-AAAA-NNNN.

    Pasos:
        1. Determinar el año de referencia.
        2. Consultar el correlativo máximo actual con bloqueo.
        3. Avanzar hasta encontrar el primer código libre.
    """
    if anio is None:
        anio = timezone.now().year
    siguiente = _siguiente_numero_lote(anio)
    while True:
        candidato = f"L-{anio}-{siguiente:04d}"
        if not Lote.objects.filter(codigo_lote=candidato).exists():
            return candidato
        siguiente += 1


@operacion("gestionar_compras")
def registrar_compra(usuario, proveedor, lineas, observacion="", fecha=None):
    """Registra una compra completa, generando detalles, lotes y movimientos de entrada.

    Pasos:
        1. Validar proveedor activo y que exista al menos una línea.
        2. Validar cada línea: producto activo, cantidad entera >= 1,
           costo >= 0 con validar_dinero, vencimiento vacío o >= hoy.
        3. Abrir transacción y crear la cabecera de Compra.
        4. Por cada línea: crear DetalleCompra, Lote y MovimientoInventario ENTRADA.
        5. Calcular y guardar el total de la compra.
        6. Devolver la Compra persistida.

    Lanza:
        ErrorDeNegocio: validación fallida o datos inconsistentes; rollback total.
    """
    # Paso 1: validar proveedor activo y al menos una línea
    if isinstance(proveedor, (int, str)):
        try:
            proveedor = Proveedor.objects.get(pk=proveedor)
        except (Proveedor.DoesNotExist, ValueError):
            raise ErrorDeNegocio("El proveedor especificado no existe.")
    elif not isinstance(proveedor, Proveedor):
        raise ErrorDeNegocio("Proveedor inválido.")

    if not proveedor.activo:
        raise ErrorDeNegocio("No se pueden registrar compras a un proveedor inactivo.")

    if not lineas:
        raise ErrorDeNegocio("La compra debe incluir al menos una línea de detalle.")

    # Paso 2: validar exhaustivamente cada línea antes de persistir
    lineas_validadas = []
    hoy = datetime.date.today()

    for idx, linea in enumerate(lineas, start=1):
        if not isinstance(linea, dict):
            raise ErrorDeNegocio(f"La línea {idx} tiene un formato inválido.")

        # Producto
        prod = linea.get("producto") or linea.get("producto_id")
        if isinstance(prod, Producto):
            producto = prod
        elif prod:
            try:
                producto = Producto.objects.get(pk=prod)
            except (Producto.DoesNotExist, ValueError):
                raise ErrorDeNegocio(f"El producto de la línea {idx} no existe.")
        else:
            raise ErrorDeNegocio(f"Debes seleccionar un producto en la línea {idx}.")

        if not producto.activo:
            raise ErrorDeNegocio(
                f"El producto '{producto.nombre}' está inactivo y no puede comprarse."
            )

        # Cantidad
        cant = linea.get("cantidad")
        if cant is None:
            cant = linea.get("cantidad_unidades")
        if isinstance(cant, bool) or cant is None:
            raise ErrorDeNegocio(f"Cantidad inválida en la línea {idx}.")
        try:
            cantidad = int(cant)
        except (TypeError, ValueError):
            raise ErrorDeNegocio(f"La cantidad en la línea {idx} debe ser un número entero.")
        if cantidad < 1:
            raise ErrorDeNegocio(
                f"La cantidad en la línea {idx} debe ser un número entero mayor o igual a 1."
            )

        # Costo unitario
        costo_raw = linea.get("costo_unitario")
        if costo_raw is None:
            raise ErrorDeNegocio(f"Debes ingresar el costo unitario en la línea {idx}.")
        try:
            if not isinstance(costo_raw, Decimal):
                costo = Decimal(str(costo_raw).strip())
            else:
                costo = costo_raw
        except (InvalidOperation, TypeError, ValueError):
            raise ErrorDeNegocio(f"El costo unitario en la línea {idx} no es un monto válido.")

        try:
            validar_dinero(costo)
        except Exception:
            raise ErrorDeNegocio(
                f"El costo unitario en la línea {idx} debe ser mayor o igual a cero y tener máximo 2 decimales."
            )

        # Fecha de vencimiento (opcional; si existe debe ser >= hoy)
        venc_raw = linea.get("fecha_vencimiento")
        if venc_raw:
            if isinstance(venc_raw, datetime.date):
                fecha_venc = venc_raw
            else:
                try:
                    fecha_venc = datetime.date.fromisoformat(str(venc_raw).strip())
                except ValueError:
                    raise ErrorDeNegocio(
                        f"Fecha de vencimiento inválida en la línea {idx}. Usa el formato AAAA-MM-DD."
                    )
            if fecha_venc < hoy:
                raise ErrorDeNegocio(
                    f"La fecha de vencimiento en la línea {idx} no puede ser anterior a la fecha actual."
                )
        else:
            fecha_venc = None

        lineas_validadas.append({
            "producto": producto,
            "cantidad": cantidad,
            "costo": costo,
            "fecha_vencimiento": fecha_venc,
        })

    # Fecha de compra
    if fecha:
        if isinstance(fecha, datetime.date):
            fecha_compra = fecha
        else:
            try:
                fecha_compra = datetime.date.fromisoformat(str(fecha).strip())
            except ValueError:
                raise ErrorDeNegocio("Fecha de compra inválida. Usa el formato AAAA-MM-DD.")
    else:
        fecha_compra = hoy

    # Paso 3: crear cabecera de Compra
    compra = Compra(
        proveedor=proveedor,
        fecha=fecha_compra,
        total=Decimal("0.00"),
        observacion=(observacion or "").strip(),
        usuario=usuario,
    )
    asignar_auditoria(compra, usuario)
    compra.full_clean()
    compra.save()

    # Paso 4: crear DetalleCompra, Lote y MovimientoInventario por cada línea
    siguiente_num = _siguiente_numero_lote(fecha_compra.year)
    total_acumulado = Decimal("0.00")

    for lin in lineas_validadas:
        subtotal = (lin["costo"] * lin["cantidad"]).quantize(Decimal("0.01"))
        total_acumulado += subtotal

        # DetalleCompra
        detalle = DetalleCompra(
            compra=compra,
            producto=lin["producto"],
            cantidad_unidades=lin["cantidad"],
            costo_unitario=lin["costo"],
            subtotal=subtotal,
        )
        detalle.full_clean()
        detalle.save()

        # Generar código de lote correlativo único
        while True:
            codigo = f"L-{fecha_compra.year}-{siguiente_num:04d}"
            siguiente_num += 1
            if not Lote.objects.filter(codigo_lote=codigo).exists():
                break

        # Lote asociado
        lote = Lote(
            producto=lin["producto"],
            detalle_compra=detalle,
            codigo_lote=codigo,
            fecha_vencimiento=lin["fecha_vencimiento"],
            cantidad_inicial=lin["cantidad"],
            cantidad_actual=lin["cantidad"],
            costo_unitario=lin["costo"],
        )
        lote.full_clean()
        lote.save()

        # MovimientoInventario de entrada
        movimiento = MovimientoInventario(
            lote=lote,
            tipo=MovimientoInventario.TipoMovimiento.ENTRADA,
            cantidad=lin["cantidad"],
            motivo=f"Compra #{compra.pk}",
            usuario=usuario,
        )
        movimiento.full_clean()
        movimiento.save()

    # Paso 5: guardar total de la compra
    compra.total = total_acumulado
    compra.full_clean()
    compra.save(update_fields=["total", "modificado_en", "modificado_por"])

    # Paso 6: devolver la Compra
    return compra


def listar_compras(usuario, desde=None, hasta=None, pagina=1):
    """Entrega la lista de compras paginada con filtros de fecha.

    Pasos:
        1. Comprobar autorización de gestionar_compras.
        2. Aplicar filtros de fecha si se proporcionan.
        3. Paginar y calcular resumen.
    """
    autorizar(usuario, "gestionar_compras")
    qs = (
        Compra.objects.select_related("proveedor", "usuario")
        .prefetch_related("detalles__producto")
        .order_by("-fecha", "-id")
    )
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)

    paginador = Paginator(qs, 15)
    page_obj = paginador.get_page(pagina)
    total_filtrado = qs.aggregate(total=Sum("total"))["total"] or Decimal("0.00")
    return page_obj, total_filtrado


def obtener_compra(usuario, pk):
    """Obtiene una compra con sus detalles y lotes.

    Pasos:
        1. Comprobar autorización de gestionar_compras.
        2. Recuperar la compra o lanzar ErrorDeNegocio si no existe.
    """
    autorizar(usuario, "gestionar_compras")
    try:
        return (
            Compra.objects.select_related("proveedor", "usuario")
            .prefetch_related("detalles__producto", "detalles__lote__movimientos")
            .get(pk=pk)
        )
    except Compra.DoesNotExist:
        raise ErrorDeNegocio("La compra solicitada no existe.")
