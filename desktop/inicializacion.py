"""Inicialización exclusiva y segura; nunca migra una instalación existente de forma implícita.

Bloque A: modo temporal experimental.
Bloque B3: persistencia segura, verificación de operador Windows y tolerancia a interrupciones.
"""
import os
from pathlib import Path
import secrets
import sqlite3
import sys

from .rutas import recursos, validar_temporal, validar_datos_instalados
from .seguridad import (
    validar_operador,
    registrar_operador,
    obtener_sid_actual,
    identificar_sid_operador,
    verificar_directorio_seguro,
)


def _validar_ruta(ruta, modo=None):
    """Resuelve y valida la ruta según el modo solicitado o deducido."""
    if modo == 'temporal':
        return validar_temporal(ruta)
    if modo == 'instalado':
        return validar_datos_instalados(ruta)
    try:
        return validar_temporal(ruta)
    except ValueError:
        return validar_datos_instalados(ruta)


def configurar(ruta, autorizar_nueva=False, solo_respaldo=False, modo=None, sid_operador=None):
    """Configura el entorno de ejecución, valida seguridad y prepara Django.

    Garantías:
    - Nunca sobreescribe secretos existentes ni regenera SECRET_KEY sobre datos existentes.
    - Rechaza instalaciones incompletas o corruptas.
    - Verifica el SID del operador autorizado en modo instalado.
    - En instalaciones nuevas autorizadas crea SQLite, .env con clave criptográfica y aplica esquema.
    - Si ya existe esquema con migraciones pendientes, bloquea el inicio funcional (exige actualización sobre copia).
    """
    destino = _validar_ruta(ruta, modo=modo)
    destino.mkdir(parents=True, exist_ok=True)
    base, entorno = destino / 'db.sqlite3', destino / '.env'
    logs_dir = destino / 'logs'
    respaldos_dir = destino / 'respaldos'
    logs_dir.mkdir(parents=True, exist_ok=True)
    respaldos_dir.mkdir(parents=True, exist_ok=True)

    nueva = not base.exists() and not entorno.exists()
    if nueva and not autorizar_nueva:
        raise ValueError('Instalación nueva: requiere --inicializar.')
    if not nueva and (not base.is_file() or not entorno.is_file()):
        raise ValueError('Instalación incompleta: conserva los archivos y revisa la configuración.')
    if base.is_symlink() or entorno.is_symlink():
        raise ValueError('Archivos de instalación inseguros.')
    if any(p.exists() and p.stat().st_nlink > 1 for p in (base, entorno)):
        raise ValueError('No se permiten enlaces físicos para datos o configuración.')

    # Validación o registro del operador Windows autorizado en modo instalado
    es_instalado = False
    try:
        validar_datos_instalados(destino)
        es_instalado = True
    except ValueError:
        es_instalado = False

    if es_instalado:
        verificar_directorio_seguro(destino, sid_esperado=sid_operador if not nueva else None)
        if not nueva:
            validar_operador(destino, sid_actual=sid_operador)

    if nueva:
        # Escritura atómica de .env mediante archivo provisional
        clave_nueva = secrets.token_urlsafe(64)
        entorno_tmp = entorno.with_suffix('.tmp')
        with entorno_tmp.open('w', encoding='utf-8') as archivo:
            archivo.write('SECRET_KEY=' + clave_nueva + '\n')
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(entorno_tmp, entorno)

        # Crear base vacía atómicamente
        with base.open('xb'):
            pass

        # Registrar operador inicial si aplica
        if es_instalado:
            sid_a_registrar = identificar_sid_operador(parametro_sid=sid_operador)
            registrar_operador(destino, sid_a_registrar)

    from dotenv import dotenv_values
    valores = dotenv_values(entorno)
    clave = valores.get('SECRET_KEY')
    if not clave or len(clave) < 50:
        raise ValueError('La configuración necesita una SECRET_KEY válida; no se regeneró.')

    os.environ.update(
        ENV_FILE=str(entorno),
        SECRET_KEY=clave,
        DATA_DIR=str(destino),
        DB_PATH=str(base),
        BACKUP_DIR=str(respaldos_dir),
        LOG_DIR=str(logs_dir),
        DJANGO_SETTINGS_MODULE='config.settings.escritorio',
        DEBUG='False',
        ALLOWED_HOSTS='127.0.0.1,localhost',
        DESKTOP_RESOURCES=str(recursos())
    )
    sys.path.insert(0, str(recursos() / 'backend'))

    import django
    from django.conf import settings
    if settings.configured:
        settings.DATA_DIR = Path(destino)
        settings.DB_PATH = Path(base)
        settings.BACKUP_DIR = respaldos_dir
        settings.LOG_DIR = logs_dir
        settings.DATABASES['default']['NAME'] = Path(base)
        if hasattr(settings, 'LOGGING') and 'handlers' in settings.LOGGING:
            if 'archivo' in settings.LOGGING['handlers']:
                settings.LOGGING['handlers']['archivo']['filename'] = logs_dir / 'sistema.log'

    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    if nueva:
        call_command('migrate', interactive=False, verbosity=0)
        call_command('cargar_datos_iniciales', verbosity=0)
    else:
        # Una consulta de esquema no autoriza a ejecutar migraciones directas.
        ejecutor = MigrationExecutor(connection)
        if ejecutor.migration_plan(ejecutor.loader.graph.leaf_nodes()) and not solo_respaldo:
            raise ValueError('Hay migraciones pendientes. Se requiere actualización autorizada sobre copia; no se migró esta base.')

    return destino


def recuperar_inicializacion_incompleta(ruta, forzar=False, modo=None, sid_operador=None):
    """Permite recuperar de forma segura una inicialización que fue interrumpida antes de crear datos.

    Condiciones:
    - Solo procede si db.sqlite3 está vacía (0 bytes) o ausente, con .env existente válido.
    - Si db.sqlite3 contiene tablas o datos, rechaza cualquier sobreescritura.
    """
    destino = _validar_ruta(ruta, modo=modo)
    base, entorno = destino / 'db.sqlite3', destino / '.env'

    if not entorno.is_file():
        raise ValueError('No se puede recuperar automáticamente sin un archivo .env previo. Restaure desde respaldo.')

    from dotenv import dotenv_values
    valores = dotenv_values(entorno)
    if not valores.get('SECRET_KEY') or len(valores.get('SECRET_KEY', '')) < 50:
        raise ValueError('El archivo .env está dañado. Restaure la clave previa para no invalidar contraseñas.')

    if base.is_file() and base.stat().st_size > 0:
        try:
            con = sqlite3.connect(base.resolve().as_uri() + '?mode=ro', uri=True)
            tablas = con.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            con.close()
            if tablas > 0:
                raise ValueError(f'La base contiene {tablas} tablas. No se puede reinicializar; los datos están protegidos.')
        except sqlite3.Error as err:
            raise ValueError(f'Error al verificar la base de datos: {err}')

    if not forzar:
        raise ValueError('Recuperación requiere confirmación explícita (forzar=True).')

    if not base.is_file():
        with base.open('xb'):
            pass

    logs_dir = destino / 'logs'
    respaldos_dir = destino / 'respaldos'
    logs_dir.mkdir(parents=True, exist_ok=True)
    respaldos_dir.mkdir(parents=True, exist_ok=True)

    # Inicializar Django con la configuración existente y correr migraciones pendientes sobre la base vacía
    clave = valores.get('SECRET_KEY')
    os.environ.update(
        ENV_FILE=str(entorno),
        SECRET_KEY=clave,
        DATA_DIR=str(destino),
        DB_PATH=str(base),
        BACKUP_DIR=str(respaldos_dir),
        LOG_DIR=str(logs_dir),
        DJANGO_SETTINGS_MODULE='config.settings.escritorio',
        DEBUG='False',
        ALLOWED_HOSTS='127.0.0.1,localhost',
        DESKTOP_RESOURCES=str(recursos())
    )
    sys.path.insert(0, str(recursos() / 'backend'))
    import django
    from django.conf import settings
    if settings.configured:
        settings.DATA_DIR = Path(destino)
        settings.DB_PATH = Path(base)
        settings.BACKUP_DIR = respaldos_dir
        settings.LOG_DIR = logs_dir
        settings.DATABASES['default']['NAME'] = Path(base)
        if hasattr(settings, 'LOGGING') and 'handlers' in settings.LOGGING:
            if 'archivo' in settings.LOGGING['handlers']:
                settings.LOGGING['handlers']['archivo']['filename'] = logs_dir / 'sistema.log'

    django.setup()
    from django.core.management import call_command
    call_command('migrate', interactive=False, verbosity=0)
    call_command('cargar_datos_iniciales', verbosity=0)
    return destino
