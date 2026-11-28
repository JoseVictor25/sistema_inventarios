"""Servicios autorizados del panel y coordinación de respaldos."""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone
import json
from apps.caja.models import Caja
from apps.caja.services import obtener_caja
from apps.inventario.services import obtener_alertas
from apps.reportes.services import ventas_agrupadas
from .operaciones import autorizar
from .permissions import tiene_permiso
from .respaldos import crear_copia, listar_copias


def _guardar_advertencia_externa(advertencia):
    ruta = settings.DATA_DIR / 'estado_respaldo_externo.json'
    try:
        if advertencia:
            ruta.write_text(json.dumps({'advertencia': advertencia}, ensure_ascii=False), encoding='utf-8')
        else:
            ruta.unlink(missing_ok=True)
    except OSError:
        pass
    settings.BACKUP_ADVERTENCIA_EXTERNA = advertencia


def datos_inicio(usuario):
    """Prepara solo los indicadores permitidos por §9.1.

    Pasos: 1. Exigir actor activo. 2. Consultar bloques autorizados.
        3. Proyectar el turno propio sin relaciones financieras diferidas.
    Lanza: PermissionDenied para actores anónimos o inactivos.
    """
    # Paso 1: sin sesión ni usuario activo no se construye el panel.
    if not usuario.is_authenticated or not usuario.is_active:
        raise PermissionDenied('No tienes acceso al panel.')
    datos = dict(caja=None)
    # Paso 2: no consultar ventas globales para el Vendedor.
    if tiene_permiso(usuario, 'ver_reportes'):
        hoy = timezone.localdate()
        resumen = ventas_agrupadas(hoy, hoy, 'dia', usuario=usuario)
        datos.update(ventas_hoy=resumen['totales']['total'], cantidad_ventas_hoy=resumen['totales']['cantidad'])
    if tiene_permiso(usuario, 'ver_stock'):
        alertas = obtener_alertas(usuario=usuario)
        # El panel cuenta productos, aunque la pantalla de alertas enumera lotes.
        cantidades = {'stock_bajo': alertas['stock_bajo'].paginator.count}
        for clave in ('por_vencer', 'vencidos'):
            cantidades[clave] = alertas[clave].paginator.object_list.order_by().values('producto_id').distinct().count()
        datos['alertas'] = [dict(nombre=nombre, cantidad=cantidades[clave]) for clave, nombre in
                           [('stock_bajo', 'Productos con stock bajo'), ('por_vencer', 'Productos por vencer'), ('vencidos', 'Productos vencidos con stock')]]
        datos.update(cantidades)
    # Paso 3: el servicio de Caja confirma propiedad y autorización.
    if tiene_permiso(usuario, 'gestionar_caja'):
        identificador = Caja.objects.filter(usuario=usuario, estado='ABIERTA').values_list('pk', flat=True).first()
        if identificador:
            caja = obtener_caja(usuario, identificador)
            datos['caja'] = dict(id=caja.pk, turno=caja.turno, fecha_apertura=caja.fecha_apertura, estado=caja.estado)
    return datos


def crear_respaldo(usuario):
    """Crea respaldo en configuración del servidor, nunca en rutas de POST.

    Pasos: 1. Autorizar. 2. Verificar motor. 3. Ejecutar copia y retención.
    Lanza: PermissionDenied o ErrorRespaldo.
    """
    autorizar(usuario, 'respaldar')
    from .respaldos import ErrorRespaldo
    if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
        raise ErrorRespaldo('El respaldo disponible requiere SQLite.')
    resultado = crear_copia(settings.DATABASES['default']['NAME'], settings.BACKUP_DIR, settings.BACKUP_CONSERVAR,
                      qr=settings.DATA_DIR / 'qr_bancario.png',
                      directorio_externo=getattr(settings, 'BACKUP_DIR_EXTERNO', None))
    _guardar_advertencia_externa(resultado['advertencia'])
    return resultado


def consultar_respaldos(usuario):
    """Pasos: 1. Autorizar listado. 2. Consultar manifiestos seguros.

    Lanza: PermissionDenied o ErrorRespaldo.
    """
    autorizar(usuario, 'respaldar')
    filas = listar_copias(settings.BACKUP_DIR)
    ultimo = next((fila['fecha'] for fila in filas if fila['verificado']), None)
    advertencia = getattr(settings, 'BACKUP_ADVERTENCIA_EXTERNA', '')
    try:
        advertencia = json.loads((settings.DATA_DIR / 'estado_respaldo_externo.json').read_text(encoding='utf-8')).get('advertencia', advertencia)
    except (OSError, ValueError, AttributeError):
        pass
    return {'filas': filas, 'directorio': str(settings.BACKUP_DIR.resolve()),
            'ultimo_verificado': ultimo,
            'externo_configurado': bool(getattr(settings, 'BACKUP_DIR_EXTERNO', None)),
            'advertencia_externa': advertencia}
