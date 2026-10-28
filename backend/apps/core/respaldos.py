"""Motor de respaldos SQLite. No importa Django ni modifica la base fuente.

El llamador web autoriza al actor. La consola es una herramienta del operador
local. El bloqueo de archivo coordina procesos, incluso creación y retención.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import time
from uuid import uuid4

logger = logging.getLogger(__name__)
PATRON = re.compile(r'^respaldo_\d{8}_\d{6}_[0-9a-f]{32}\.sqlite3$')
TABLAS = {'django_migrations', 'usuarios_usuario', 'usuarios_rol', 'usuarios_permiso',
          'catalogo_producto', 'inventario_lote', 'ventas_venta', 'compras_compra', 'caja_caja', 'auditoria_logauditoria'}


class ErrorRespaldo(Exception):
    """Error operativo que puede mostrarse sin revelar datos ni credenciales."""


def hash_archivo(ruta):
    digest = hashlib.sha256()
    with Path(ruta).open('rb') as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b''):
            digest.update(bloque)
    return digest.hexdigest()


def _regular(ruta):
    return ruta.is_file() and not ruta.is_symlink() and not (hasattr(ruta, 'is_junction') and ruta.is_junction())


def verificar_copia(ruta):
    """Verifica contenido SQLite sin ejecutar migraciones.

    Pasos: 1. Abrir solo lectura. 2. Revisar integridad, FK y tablas. 3. Hash.
    Lanza: ErrorRespaldo si no es una copia íntegra del sistema.
    """
    ruta = Path(ruta)
    if not _regular(ruta):
        raise ErrorRespaldo('El archivo de respaldo no es un archivo regular válido.')
    try:
        # Paso 1: mode=ro impide crear accidentalmente una base inexistente.
        conexion = sqlite3.connect(ruta.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            # Paso 2: integrity_check no sustituye foreign_key_check.
            if conexion.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ErrorRespaldo('La copia no superó la verificación de integridad.')
            if conexion.execute('PRAGMA foreign_key_check').fetchone():
                raise ErrorRespaldo('La copia contiene relaciones inconsistentes.')
            tablas = {r[0] for r in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not TABLAS <= tablas:
                raise ErrorRespaldo('La copia no contiene las tablas esenciales del sistema.')
            migraciones = list(conexion.execute('SELECT app, name FROM django_migrations ORDER BY app, name'))
        finally:
            conexion.close()
        # Paso 3: el hash corresponde al archivo cerrado, no a la fuente activa.
        return dict(tamano=ruta.stat().st_size, sha256=hash_archivo(ruta), migraciones=migraciones)
    except (OSError, sqlite3.Error):
        logger.exception('Fallo al verificar copia SQLite')
        raise ErrorRespaldo('No se pudo leer o verificar la copia SQLite.') from None


@contextmanager
def _bloqueo(directorio):
    archivo = directorio / '.respaldos.lock'
    if archivo.is_symlink():
        raise ErrorRespaldo('El archivo de control no es seguro.')
    manejador = archivo.open('a+b')
    tomado = False
    try:
        if manejador.seek(0, 2) == 0:
            manejador.write(b'0')
            manejador.flush()
        manejador.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(manejador.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(manejador.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            tomado = True
        except OSError:
            raise ErrorRespaldo('Hay otra operación de respaldo en curso. Intenta nuevamente al finalizar.') from None
        yield
    finally:
        if tomado:
            manejador.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(manejador.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(manejador.fileno(), fcntl.LOCK_UN)
        manejador.close()


def _publicar(provisional, final):
    # Windows rename falla si el destino existe. POSIX link también es exclusivo.
    if os.name == 'nt':
        os.rename(provisional, final)
    else:
        os.link(provisional, final)
        provisional.unlink()


def _metadatos(ruta, origen=None):
    if not PATRON.fullmatch(ruta.name) or not _regular(ruta):
        return None
    if origen and (ruta.resolve() == origen or os.path.samefile(ruta, origen)):
        return None
    manifiesto = ruta.with_suffix('.json')
    if not _regular(manifiesto):
        return None
    try:
        datos = json.loads(manifiesto.read_text(encoding='utf-8'))
        if not isinstance(datos, dict) or datos.get('motor') != 'inventarios-backup-v1' or datos.get('archivo') != ruta.name:
            return None
        if datos.get('tamano') != ruta.stat().st_size or datos.get('sha256') != hash_archivo(ruta):
            return None
        fecha = datetime.fromisoformat(datos['fecha'])
        if fecha.tzinfo is None:
            return None
        return datos
    except (OSError, ValueError, KeyError, TypeError):
        return None


def listar_copias(directorio):
    """Lista metadatos seguros; no adopta ni elimina archivos desconocidos.

    Pasos: 1. Resolver directorio. 2. Comprobar manifiestos y hash. 3. Ordenar.
    Lanza: ErrorRespaldo si no se puede acceder al directorio.
    """
    directorio = Path(directorio).resolve()
    if not directorio.exists():
        return []
    try:
        filas = []
        for ruta in directorio.glob('*.sqlite3'):
            if not _regular(ruta):
                continue
            datos = _metadatos(ruta)
            filas.append(dict(nombre=ruta.name, tamano=ruta.stat().st_size,
                fecha=datos['fecha'] if datos else None, sha256=datos['sha256'] if datos else None,
                verificado=bool(datos)))
        return sorted(filas, key=lambda r: (r['fecha'] or '', r['nombre']), reverse=True)
    except OSError:
        raise ErrorRespaldo('No se pudo consultar la carpeta de respaldos.') from None


def _retener(directorio, conservar, origen):
    candidatos = []
    for ruta in directorio.glob('respaldo_*.sqlite3'):
        datos = _metadatos(ruta, origen)
        if datos:
            try:
                verificar_copia(ruta)
            except ErrorRespaldo:
                continue
            candidatos.append((datos['fecha'], ruta.name, ruta))
    for _, _, ruta in sorted(candidatos, reverse=True)[conservar:]:
        # Solo archivos gestionados, verificados y dentro del directorio resuelto.
        if ruta.resolve().parent != directorio or ruta.resolve() == origen:
            raise ErrorRespaldo('Se rechazó una ruta insegura durante la retención.')
        ruta.unlink()
        ruta.with_suffix('.json').unlink()
        logger.info('Retención: eliminado respaldo gestionado %s', ruta.name)


def crear_copia(origen, directorio, conservar, *, limite_segundos=120):
    """Publica una copia consistente y luego aplica retención segura.

    Pasos: 1. Validar rutas/configuración. 2. Bloquear entre procesos.
        3. Copiar con API SQLite. 4. Verificar/publicar. 5. Retener y registrar.
    Lanza: ErrorRespaldo; nunca migra ni escribe en la base fuente.
    """
    # Paso 1: validar antes de abrir conexiones o crear el directorio destino.
    origen = Path(origen).resolve()
    directorio = Path(directorio).resolve()
    if not _regular(origen) or not isinstance(conservar, int) or isinstance(conservar, bool) or conservar < 1:
        raise ErrorRespaldo('La base fuente debe existir y la retención debe ser un entero positivo.')
    if directorio == origen or directorio == origen.parent:
        raise ErrorRespaldo('Usa una carpeta de respaldos distinta de la carpeta de la base activa.')
    if limite_segundos <= 0:
        raise ErrorRespaldo('El tiempo máximo de respaldo debe ser positivo.')
    propios = []
    try:
        directorio.mkdir(parents=True, exist_ok=True)
        # Paso 2: el mismo bloqueo cubre publicación y retención.
        with _bloqueo(directorio):
            fecha = datetime.now(timezone.utc)
            nombre = f'respaldo_{fecha:%Y%m%d_%H%M%S}_{uuid4().hex}.sqlite3'
            final = directorio / nombre
            if final.exists() or final.with_suffix('.json').exists():
                raise ErrorRespaldo('El nombre ya existe; no se sobrescribió ningún respaldo.')
            provisional = directorio / (nombre + '.partial')
            with provisional.open('xb'):
                pass
            propios.append(provisional)
            # Paso 3: copia independiente; no utilizar la conexión ORM transaccional.
            inicio = time.monotonic()
            def progreso(estado, restantes, total):
                if time.monotonic() - inicio > limite_segundos:
                    raise ErrorRespaldo('La copia excedió el tiempo permitido; los respaldos anteriores se conservan.')
            fuente = sqlite3.connect(origen.as_uri() + '?mode=ro', uri=True)
            try:
                destino = sqlite3.connect(provisional)
                try:
                    fuente.backup(destino, pages=256, progress=progreso, sleep=.05)
                finally:
                    destino.close()
            finally:
                fuente.close()
            # Paso 4: solo la copia íntegra obtiene nombre final y manifiesto.
            datos = verificar_copia(provisional)
            datos.update(motor='inventarios-backup-v1', archivo=nombre, fecha=fecha.isoformat())
            meta_provisional = directorio / (nombre + '.json.partial')
            with meta_provisional.open('x', encoding='utf-8') as archivo:
                propios.append(meta_provisional)
                json.dump(datos, archivo, ensure_ascii=False, indent=2)
                archivo.flush()
                os.fsync(archivo.fileno())
            _publicar(provisional, final)
            _publicar(meta_provisional, final.with_suffix('.json'))
            # Paso 5: no borrar copias anteriores si la nueva no fue publicada.
            advertencia = ''
            try:
                _retener(directorio, conservar, origen)
            except (OSError, ErrorRespaldo):
                logger.exception('Respaldo creado; retención incompleta')
                advertencia = 'Respaldo creado y verificado; no se pudo completar la retención.'
            logger.info('Respaldo verificado: %s, bytes=%s, sha256=%s', nombre, datos['tamano'], datos['sha256'])
            return dict(datos, advertencia=advertencia)
    except ErrorRespaldo as error:
        logger.warning('Respaldo no completado: %s', error)
        raise
    except (OSError, sqlite3.Error):
        logger.exception('No se pudo completar el respaldo SQLite')
        raise ErrorRespaldo('No se pudo completar el respaldo. Revisa espacio disponible y permisos; las copias anteriores se conservan.') from None
    finally:
        for ruta in propios:
            if ruta.exists():
                try:
                    ruta.unlink()
                except OSError:
                    logger.warning('No se pudo retirar un archivo provisional de respaldo')
