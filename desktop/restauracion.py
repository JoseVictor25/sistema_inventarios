"""Restauración transaccional de una base instalada desde un respaldo verificado."""
import os
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile

from apps.core.respaldos import (ErrorRespaldo, _metadatos, _qr_manifiesto,
    crear_copia, verificar_copia)
from .bloqueo_instancia import BloqueoInstanciaActiva, bloqueo_instancia


def restaurar_con_bloqueo(copia, directorio_datos, db=None, directorio_respaldos=None,
                           conservar=None, qr_actual=None, *, preparar=None):
    """Camino CLI real: prepara y restaura dentro del cerrojo de instancia."""
    try:
        with bloqueo_instancia(Path(directorio_datos)):
            if preparar is not None:
                preparar()
                from django.conf import settings
                from django.db import connections
                connections.close_all()
                db = settings.DB_PATH
                directorio_respaldos = settings.BACKUP_DIR
                conservar = settings.BACKUP_CONSERVAR
                qr_actual = settings.DATA_DIR / 'qr_bancario.png'
            return restaurar(copia, db, directorio_respaldos, conservar, qr_actual)
    except BloqueoInstanciaActiva as error:
        raise ErrorRespaldo(f'No se puede restaurar mientras el programa está en ejecución: {error}') from error
    except OSError as error:
        raise ErrorRespaldo(f'No se pudo restaurar por un error del sistema: {error}') from error


def restaurar(copia, db, directorio_respaldos, conservar, qr_actual=None):
    """Prepara/verifica todo antes del replace; necesita bloqueo de instancia del llamador."""
    copia, db = Path(copia).resolve(), Path(db).resolve()
    meta = _metadatos(copia)
    if meta is None:
        raise ErrorRespaldo('El respaldo o su manifiesto no son válidos.')
    verificacion = verificar_copia(copia)
    if verificacion['sha256'] != meta['sha256']:
        raise ErrorRespaldo('El hash del respaldo no coincide con el manifiesto.')
    copia_seguridad = crear_copia(db, directorio_respaldos, conservar, qr=qr_actual)
    seguridad = Path(directorio_respaldos) / copia_seguridad['archivo']
    qr_bytes = _qr_manifiesto(meta)
    temporal = None
    qr_temp = None
    qr_actual = Path(qr_actual) if qr_actual else None
    qr_previo = None
    if qr_actual and qr_actual.exists():
        qr_previo = qr_actual.read_bytes()
    try:
        fd, nombre = tempfile.mkstemp(prefix='db_restaurada_', suffix='.sqlite3', dir=db.parent)
        os.close(fd)
        temporal = Path(nombre)
        shutil.copyfile(copia, temporal)
        if verificar_copia(temporal)['sha256'] != meta['sha256']:
            raise ErrorRespaldo('La copia cambió mientras se preparaba la restauración.')
        if qr_bytes is not None and qr_actual:
            fd, nombre = tempfile.mkstemp(prefix='qr_restaurado_', suffix='.tmp', dir=qr_actual.parent)
            os.close(fd)
            qr_temp = Path(nombre)
            qr_temp.write_bytes(qr_bytes)
        # Vaciar WAL antes del replace. La copia de seguridad ya quedó publicada.
        with closing(sqlite3.connect(db)) as conexion:
            conexion.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        os.replace(temporal, db)
        temporal = None
        for sufijo in ('-wal', '-shm'):
            Path(str(db) + sufijo).unlink(missing_ok=True)
        if qr_temp:
            os.replace(qr_temp, qr_actual)
            qr_temp = None
        return {'base': str(db), 'respaldo_seguridad': copia_seguridad['archivo'],
                'qr_restaurado': qr_bytes is not None and qr_actual is not None}
    except Exception as error:
        # Restaurar base anterior desde la copia independiente, aunque falle el QR.
        rollback = db.with_name(db.name + '.rollback.tmp')
        try:
            shutil.copyfile(seguridad, rollback)
            os.replace(rollback, db)
            for sufijo in ('-wal', '-shm'):
                Path(str(db) + sufijo).unlink(missing_ok=True)
            if qr_actual and qr_previo is not None:
                restaurar_qr = qr_actual.with_name(qr_actual.name + '.rollback.tmp')
                restaurar_qr.write_bytes(qr_previo)
                os.replace(restaurar_qr, qr_actual)
        except Exception as rollback_error:
            raise ErrorRespaldo(f'Falló la restauración y la recuperación automática: {rollback_error}') from error
        if isinstance(error, ErrorRespaldo):
            raise
        raise ErrorRespaldo(f'No se pudo completar la restauración; la base anterior fue recuperada: {error}') from error
    finally:
        if temporal:
            temporal.unlink(missing_ok=True)
        if qr_temp:
            qr_temp.unlink(missing_ok=True)
