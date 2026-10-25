"""Lógica de negocio de inventario. Las vistas llaman a estas funciones;
así la lógica se prueba fácil y no se duplica."""
import hashlib
import json
import uuid
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F, Q, Sum, Value, IntegerField
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.auditoria.services import registrar_cambio
from apps.catalogo.models import Producto
from apps.core.exceptions import ErrorDeNegocio
from apps.core.operaciones import autorizar
from apps.core.permissions import tiene_permiso
from .forms import FiltroStockForm, FiltroLoteForm, FiltroMovimientoForm, FiltroAlertasForm
from .models import Lote, MovimientoInventario, OperacionAjusteInventario


def _validar_filtros(clase, filtros):
    form = clase(filtros or {})
    if not form.is_valid():
        raise ErrorDeNegocio(' '.join(str(e) for errores in form.errors.values() for e in errores))
    return form.cleaned_data


def _stock():
    hoy = timezone.localdate()
    vigente = Q(lotes__fecha_vencimiento__isnull=True) | Q(lotes__fecha_vencimiento__gte=hoy)
    # Un único join de lotes: nunca sumar tras unir presentaciones o movimientos.
    return Producto.objects.annotate(
        stock_total=Coalesce(Sum('lotes__cantidad_actual'), Value(0), output_field=IntegerField()),
        stock_disponible=Coalesce(Sum('lotes__cantidad_actual', filter=vigente), Value(0), output_field=IntegerField()),
    ).filter(Q(activo=True) | Q(stock_total__gt=0)).order_by('nombre', 'pk')


def _filas_stock(consulta):
    # Diccionarios: no colisionar con la property stock_actual ni filtrar relaciones privadas.
    return consulta.values('id', 'codigo', 'nombre', 'activo', 'stock_minimo',
                           'categoria__nombre', 'stock_disponible', stock_actual=F('stock_total'))


def listar_stock(usuario, filtros=None):
    """Consulta existencias físicas y vigentes sin consultas por producto.

    Pasos: 1. Autorizar y validar filtros. 2. Agregar lotes y paginar.
    Lanza: PermissionDenied o ErrorDeNegocio por filtros inválidos.
    """
    # Paso 1: los servicios también comprueban permisos.
    autorizar(usuario, 'ver_stock')
    datos = _validar_filtros(FiltroStockForm, filtros)
    # Paso 2: stock bajo incluye cero; los inactivos con existencias se conservan.
    consulta = _stock()
    if datos.get('q'):
        consulta = consulta.filter(Q(codigo__icontains=datos['q']) | Q(nombre__icontains=datos['q']))
    if datos.get('solo_bajo') == '1':
        consulta = consulta.filter(stock_total__lte=F('stock_minimo'))
    return Paginator(_filas_stock(consulta), 20).get_page(datos.get('page') or 1)


def _filas_lotes(usuario, consulta):
    campos = ['id', 'producto_id', 'producto__codigo', 'producto__nombre', 'producto__activo',
              'codigo_lote', 'cantidad_inicial', 'cantidad_actual', 'fecha_vencimiento']
    if tiene_permiso(usuario, 'ver_costos'):
        campos.append('costo_unitario')
    return consulta.values(*campos)


def listar_lotes(usuario, filtros=None):
    """Entrega lotes, incluidos agotados e históricos, con costos autorizados.

    Pasos: 1. Autorizar/validar. 2. Filtrar por producto y estado. 3. Paginar.
    Lanza: PermissionDenied o ErrorDeNegocio.
    """
    # Paso 1: no devolver instancias con acceso diferido a costos.
    autorizar(usuario, 'ver_stock')
    datos = _validar_filtros(FiltroLoteForm, filtros)
    # Paso 2: hoy se calcula en la zona de Django.
    hoy = timezone.localdate()
    consulta = Lote.objects.order_by(F('fecha_vencimiento').asc(nulls_last=True), 'pk')
    if datos.get('q'):
        consulta = consulta.filter(Q(codigo_lote__icontains=datos['q']) |
            Q(producto__nombre__icontains=datos['q']) | Q(producto__codigo__icontains=datos['q']))
    if datos.get('producto'):
        consulta = consulta.filter(producto_id=datos['producto'])
    estado = datos.get('estado')
    if estado in ('vigente', 'por_vencer', 'vencido'):
        consulta = consulta.filter(cantidad_actual__gt=0)
    if estado == 'vigente':
        consulta = consulta.filter(Q(fecha_vencimiento__isnull=True) | Q(fecha_vencimiento__gte=hoy))
    elif estado == 'por_vencer':
        consulta = consulta.filter(fecha_vencimiento__range=(hoy, hoy + timedelta(days=settings.DIAS_ALERTA_VENCIMIENTO)))
    elif estado == 'vencido':
        consulta = consulta.filter(fecha_vencimiento__lt=hoy)
    elif estado == 'sin_fecha':
        consulta = consulta.filter(fecha_vencimiento__isnull=True)
    elif estado == 'agotado':
        consulta = consulta.filter(cantidad_actual=0)
    # Paso 3: las proyecciones no contienen el costo sin su permiso.
    return Paginator(_filas_lotes(usuario, consulta), 20).get_page(datos.get('page') or 1)


def listar_movimientos(usuario, filtros=None):
    """Consulta historial operativo, separado de la bitácora de auditoría.

    Pasos: 1. Autorizar/validar. 2. Filtrar con fechas locales. 3. Proyectar y paginar.
    Lanza: PermissionDenied o ErrorDeNegocio.
    """
    # Paso 1: consultar movimientos no exige ver_auditoria.
    autorizar(usuario, 'ver_stock')
    datos = _validar_filtros(FiltroMovimientoForm, filtros)
    # Paso 2: intervalos aware; hasta incluye el día completo.
    consulta = MovimientoInventario.objects.order_by('-fecha', '-pk')
    if datos.get('q'):
        consulta = consulta.filter(Q(lote__codigo_lote__icontains=datos['q']) |
            Q(lote__producto__nombre__icontains=datos['q']) | Q(lote__producto__codigo__icontains=datos['q']))
    for entrada, campo in [('producto', 'lote__producto_id'), ('lote', 'lote_id'), ('tipo', 'tipo')]:
        if datos.get(entrada):
            consulta = consulta.filter(**{campo: datos[entrada]})
    if datos.get('desde'):
        consulta = consulta.filter(fecha__gte=timezone.make_aware(datetime.combine(datos['desde'], time.min)))
    if datos.get('hasta'):
        # Evitar desbordamiento si el usuario envía 9999-12-31.
        if datos['hasta'].year == 9999 and datos['hasta'].month == 12 and datos['hasta'].day == 31:
            raise ErrorDeNegocio('La fecha final está fuera del rango admitido.')
        consulta = consulta.filter(fecha__lt=timezone.make_aware(datetime.combine(datos['hasta'] + timedelta(days=1), time.min)))
    # Paso 3: no exponer la instancia lote ni costos a través del contexto.
    filas = consulta.values('id', 'lote_id', 'lote__codigo_lote', 'lote__producto__nombre',
        'lote__producto__codigo', 'tipo', 'cantidad', 'fecha', 'motivo', 'usuario__username')
    return Paginator(filas, 20).get_page(datos.get('page') or 1)


def obtener_alertas(*, usuario, filtros=None):
    """Tres grupos de alertas independientes, paginados de veinte en veinte.

    Pasos: 1. Autorizar/validar. 2. Calcular límites. 3. Paginar cada grupo.
    Lanza: PermissionDenied o ErrorDeNegocio.
    """
    # Paso 1: sin escrituras ni permisos nuevos para el Vendedor.
    autorizar(usuario, 'ver_stock')
    datos = _validar_filtros(FiltroAlertasForm, filtros)
    # Paso 2: lotes agotados y sin fecha nunca generan alertas de vencimiento.
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=settings.DIAS_ALERTA_VENCIMIENTO)
    bajo = _filas_stock(_stock().filter(stock_total__lte=F('stock_minimo')))
    lotes = Lote.objects.filter(cantidad_actual__gt=0).order_by('fecha_vencimiento', 'pk')
    # Paso 3: cada lista tiene su propia página; no truncar alertas silenciosamente.
    return {
        'stock_bajo': Paginator(bajo, 20).get_page(datos.get('page_bajo') or 1),
        'por_vencer': Paginator(_filas_lotes(usuario, lotes.filter(fecha_vencimiento__range=(hoy, limite))), 20).get_page(datos.get('page_por_vencer') or 1),
        'vencidos': Paginator(_filas_lotes(usuario, lotes.filter(fecha_vencimiento__lt=hoy)), 20).get_page(datos.get('page_vencidos') or 1),
        'dias_alerta': settings.DIAS_ALERTA_VENCIMIENTO,
    }


def obtener_lote_para_ajuste(usuario, identificador):
    """Selecciona un lote sin costos para el formulario autorizado.

    Pasos: 1. Autorizar. 2. Proyectar solo identificación y cantidades.
    Lanza: PermissionDenied o ErrorDeNegocio por lote inexistente.
    """
    # Paso 1: el selector de ajustes exige el mismo permiso que la escritura.
    autorizar(usuario, 'ajustar_inventario')
    # Paso 2: no cargar relaciones financieras ni costos para una elección.
    lote = Lote.objects.filter(pk=identificador).values('id', 'codigo_lote', 'producto__nombre',
        'producto__codigo', 'producto__activo', 'cantidad_actual', 'cantidad_inicial', 'fecha_vencimiento').first()
    if lote is None:
        raise ErrorDeNegocio('El lote indicado no existe.')
    return lote


def _calcular_huella(usuario_id, lote_id, tipo, cantidad, motivo):
    """Huella SHA-256 canónica de usuario, lote, tipo, cantidad y motivo normalizado."""
    contenido = {
        "cantidad": int(cantidad),
        "lote_id": int(lote_id),
        "motivo": str(motivo).strip(),
        "tipo": str(tipo).strip(),
        "usuario_id": int(usuario_id),
    }
    return hashlib.sha256(
        json.dumps(contenido, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def ajustar_inventario(usuario, lote, tipo, cantidad, motivo, *, clave=None):
    """Actualiza existencias, movimiento, auditoría y registro de idempotencia en una transacción.

    Pasos: 1. Autorizar y validar. 2. Identificar lote y validar/generar UUID clave.
        3. Calcular huella SHA-256 canónica. 4. Recuperar operación previa confirmada.
        5. En transacción atómica: reservar clave, CAS sobre Lote, crear Movimiento,
        registrar LogAuditoria, enlazar a OperacionAjusteInventario y confirmar todo junto.
    Lanza: PermissionDenied o ErrorDeNegocio.
    """
    # Paso 1: cantidades con signo; el actor nunca procede del formulario.
    autorizar(usuario, 'ajustar_inventario')
    if tipo not in ('AJUSTE', 'MERMA'):
        raise ErrorDeNegocio('Solo se permiten ajustes o mermas.')
    if isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad == 0:
        raise ErrorDeNegocio('La cantidad debe ser un entero distinto de cero.')
    if tipo == 'MERMA' and cantidad >= 0:
        raise ErrorDeNegocio('Una merma requiere una cantidad negativa.')
    if not isinstance(motivo, str) or not 5 <= len(motivo.strip()) <= 200:
        raise ErrorDeNegocio('El motivo debe tener entre 5 y 200 caracteres.')
    motivo_limpio = motivo.strip()
    identificador = lote.pk if isinstance(lote, Lote) else lote
    if isinstance(identificador, bool) or not isinstance(identificador, int) or not 0 < identificador <= 9223372036854775807:
        raise ErrorDeNegocio('El identificador del lote no es válido.')

    # Paso 2: comprobar existencia del lote
    try:
        actual = Lote.objects.get(pk=identificador)
    except Lote.DoesNotExist:
        raise ErrorDeNegocio('El lote indicado no existe.')

    # Validar o generar clave UUID
    if clave is None:
        clave = uuid.uuid4()
    elif isinstance(clave, str):
        try:
            clave = uuid.UUID(clave)
        except (ValueError, TypeError, AttributeError):
            raise ErrorDeNegocio('La clave de idempotencia no es válida.')
    elif not isinstance(clave, uuid.UUID):
        raise ErrorDeNegocio('La clave de idempotencia no es válida.')

    # Paso 3: calcular huella canónica SHA-256
    huella = _calcular_huella(usuario.pk, identificador, tipo, cantidad, motivo_limpio)

    # Paso 4: comprobar si ya existe una operación confirmada con esta clave
    previa = OperacionAjusteInventario.objects.select_related(
        'movimiento', 'movimiento__lote', 'auditoria'
    ).filter(clave=clave).first()
    if previa is not None and previa.movimiento is not None:
        if previa.usuario_id != usuario.pk or previa.huella != huella:
            raise ErrorDeNegocio('La clave ya fue utilizada con otros datos. Actualiza la página.')
        return previa.movimiento

    # Paso 5: ejecución atómica completa con reserva de idempotencia
    try:
        with transaction.atomic():
            # Intentar reservar la clave de idempotencia
            try:
                with transaction.atomic():
                    operacion = OperacionAjusteInventario.objects.create(
                        clave=clave,
                        usuario=usuario,
                        lote=actual,
                        tipo=tipo,
                        huella=huella,
                    )
            except IntegrityError:
                previa = OperacionAjusteInventario.objects.select_related(
                    'movimiento', 'movimiento__lote', 'auditoria'
                ).filter(clave=clave).first()
                if previa is None:
                    raise
                if (previa.usuario_id, previa.huella) != (usuario.pk, huella):
                    raise ErrorDeNegocio('La clave ya fue utilizada con otros datos. Actualiza la página.')
                if previa.movimiento is None:
                    raise ErrorDeNegocio('Otra operación con esta clave no se completó. Intenta de nuevo.')
                return previa.movimiento

            # Releer lote y verificar stock resultante
            actual.refresh_from_db()
            anterior = actual.cantidad_actual
            nueva = anterior + cantidad
            if not 0 <= nueva <= actual.cantidad_inicial:
                raise ErrorDeNegocio(f'El lote tiene {anterior} unidades. El resultado debe estar entre 0 y {actual.cantidad_inicial}.')

            # CAS para evitar sobrescritura concurrente
            filas = Lote.objects.filter(
                pk=actual.pk, cantidad_actual=anterior, cantidad_inicial__gte=nueva
            ).update(cantidad_actual=F('cantidad_actual') + cantidad)
            if filas != 1:
                raise ErrorDeNegocio('El lote cambió durante la operación. Actualiza la página y revisa las cantidades.')

            # Registro histórico inmutable
            movimiento = MovimientoInventario(
                lote=actual, tipo=tipo, cantidad=cantidad, motivo=motivo_limpio, usuario=usuario
            )
            movimiento.full_clean()
            movimiento.save()

            # Bitácora de auditoría
            auditoria = registrar_cambio(
                usuario, 'AJUSTE_INVENTARIO', 'Lote', actual.pk,
                {'cantidad_actual': anterior},
                {
                    'cantidad_actual': nueva,
                    'producto_id': actual.producto_id,
                    'movimiento_id': movimiento.pk,
                    'tipo': tipo,
                    'cantidad': cantidad,
                    'motivo': motivo_limpio,
                }
            )

            # Enlazar movimiento y auditoría al registro de idempotencia
            operacion.movimiento = movimiento
            operacion.auditoria = auditoria
            operacion.full_clean()
            operacion.save(update_fields=['movimiento', 'auditoria'])
            return movimiento
    except Lote.DoesNotExist:
        raise ErrorDeNegocio('El lote indicado no existe.') from None
    except ValidationError as error:
        raise ErrorDeNegocio(' '.join(error.messages)) from None
    except IntegrityError:
        raise ErrorDeNegocio('No se pudo registrar el ajuste por un conflicto de integridad.') from None
    except OperationalError as error:
        if not any(texto in str(error).lower() for texto in ('locked', 'busy')):
            raise
        raise ErrorDeNegocio('Otra operación está actualizando el inventario. Actualiza la página y revisa el historial antes de reintentar.') from None



def descontar_stock_fefo(producto, unidades):
    """Descuenta `unidades` del producto, empezando por el lote que vence primero.

    Pasos:
        1. Validar que `unidades` sea un entero mayor que cero.
        2. Bloquear los lotes con stock y no vencidos (evita que dos ventas
           simultáneas tomen las mismas unidades).
        3. Comprobar que el stock total alcance.
        4. Recorrer los lotes por fecha de vencimiento y descontar de cada uno.
        5. Devolver de qué lote salió cada cantidad (para calcular costo y ganancia).

    Lanza:
        ErrorDeNegocio: si las unidades no son válidas o el stock no alcanza.

    Debe llamarse dentro de `transaction.atomic()`.
    """
    # Paso 1: validar la entrada
    if not isinstance(unidades, int) or isinstance(unidades, bool) or unidades <= 0:
        raise ErrorDeNegocio("La cantidad a descontar debe ser un número entero mayor que cero.")

    # Paso 2: lotes disponibles, el que vence antes primero (RN-06 y RN-07)
    try:
        lotes = list(
            Lote.objects.select_for_update()
            .filter(producto=producto, cantidad_actual__gt=0)
            .exclude(fecha_vencimiento__lt=timezone.localdate())
            .order_by(F("fecha_vencimiento").asc(nulls_last=True), "id")
        )

        # Paso 3: comprobar el stock
        disponible = sum(lote.cantidad_actual for lote in lotes)
        if disponible < unidades:
            raise ErrorDeNegocio(
                f"No alcanza el stock de {producto.nombre}: quedan {disponible} unidades."
            )

        # Paso 4: descontar lote por lote
        restante = unidades
        salidas = []
        for lote in lotes:
            tomar = min(lote.cantidad_actual, restante)
            lote.cantidad_actual -= tomar
            lote.save(update_fields=["cantidad_actual"])
            salidas.append((lote, tomar))
            restante -= tomar
            if restante == 0:
                break

        # Paso 5: informar de dónde salió cada cantidad
        return salidas
    except OperationalError as error:
        if not any(texto in str(error).lower() for texto in ("locked", "busy")):
            raise
        raise ErrorDeNegocio("El inventario está siendo actualizado por otra operación. Reintenta.") from None
