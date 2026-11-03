"""Mantenimiento seguro del ciclo de vida y actualizaciones en Windows (Bloque B3).

Flujo de actualización segura:
1. Detectar instalación previa y versión instalada.
2. Detectar procesos activos y respaldos en curso (bloqueo no destructivo).
3. Evitar actualizaciones mientras existan operaciones activas.
4. Rechazar downgrades incompatibles.
5. Ensayar migraciones exclusivamente sobre copias temporales aisladas (NUNCA sobre la base real).
6. Crear un respaldo verificado antes de cualquier operación autorizada.
7. Conservar configuración, usuarios, datos y registros.
8. Proveer procedimiento documentado de recuperación y rollback.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

from .rutas import validar_datos_instalados, resolver_rutas, recursos
from .seguridad import leer_registro_operador


def parsear_version(version_str):
    """Convierte cadena de versión semántica 'X.Y.Z' a tupla de enteros."""
    if not version_str or not isinstance(version_str, str):
        return (0, 0, 0)
    partes = []
    for p in version_str.split('.'):
        num = ''
        for c in p:
            if c.isdigit():
                num += c
            else:
                break
        partes.append(int(num) if num else 0)
    while len(partes) < 3:
        partes.append(0)
    return tuple(partes[:3])


def detectar_instalacion_previa(directorio_datos):
    """Inspecciona la presencia de una instalación previa en el directorio de datos."""
    rutas = resolver_rutas(directorio_datos)
    datos_dir = rutas['datos']
    db = rutas['db']
    env = rutas['env']
    operador = rutas['operador']

    instalada = db.is_file() and env.is_file()
    registro = leer_registro_operador(datos_dir) if operador.is_file() else None
    version = registro.get('version', '0.0.0') if registro else '0.0.0'

    return {
        'instalada': instalada,
        'ruta': datos_dir,
        'version': version,
        'operador_sid': registro.get('sid') if registro else None,
        'cuenta': registro.get('cuenta') if registro else None,
        'db_existe': db.is_file(),
        'env_existe': env.is_file(),
        'tamano_db': db.stat().st_size if db.is_file() else 0,
    }


def detectar_procesos_activos(directorio_datos):
    """Comprueba si la aplicación, su servidor HTTP o un proceso de respaldo están activos.

    Fuentes de detección (en orden):
    1. Archivos `.partial` en respaldos/: respaldo en curso.
    2. Cerrojo `.instancia.lock`: instancia del servidor activa (launcher + Waitress).
    3. Cerrojo `.respaldos.lock`: operación de respaldo activa exclusivamente.

    Limitación documentada (B4): no detecta el nombre del proceso ejecutable
    directamente. La detección se basa en cerrojos de archivo coordinados.
    """
    from .bloqueo_instancia import detectar_instancia_activa, NOMBRE_LOCK

    rutas = resolver_rutas(directorio_datos)
    directorio = rutas['datos']
    respaldos_dir = rutas['respaldos']
    lock_file = rutas['lock']

    # 1. Archivos parciales de respaldo en curso
    if respaldos_dir.is_dir():
        parciales = list(respaldos_dir.glob('*.partial'))
        if parciales:
            return True, f'Hay un archivo de respaldo temporal en curso: {parciales[0].name}'

    # 2. Cerrojo de instancia activa (cubre servidor HTTP + proceso principal)
    activa, razon_instancia = detectar_instancia_activa(directorio)
    if activa:
        return True, razon_instancia

    # 3. Cerrojo de respaldos (separado del lock de instancia)
    if not lock_file.exists():
        return False, 'Sin procesos activos.'

    try:
        manejador = lock_file.open('a+b')
    except OSError as exc:
        return True, f'El archivo de control de respaldos está retenido: {exc}'

    try:
        manejador.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(manejador.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(manejador.fileno(), msvcrt.LK_UNLCK, 1)
                return False, 'Sin procesos activos.'
            except OSError:
                return True, 'Hay una operación de respaldo en ejecución.'
        else:
            import fcntl
            try:
                fcntl.flock(manejador.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(manejador.fileno(), fcntl.LOCK_UN)
                return False, 'Sin procesos activos.'
            except OSError:
                return True, 'Hay una operación de respaldo en ejecución.'
    finally:
        manejador.close()


def verificar_compatibilidad_version(version_instalada, version_nueva):
    """Valida versiones semánticas y bloquea downgrades."""
    v_actual = parsear_version(version_instalada)
    v_nueva = parsear_version(version_nueva)
    if v_nueva < v_actual:
        raise ValueError(
            f'Downgrade no permitido: la versión actualmente instalada ({version_instalada}) '
            f'es superior a la que se intenta instalar ({version_nueva}).'
        )
    return True


def crear_respaldo_seguridad(directorio_datos):
    """Crea un respaldo íntegro y verificado antes de una actualización."""
    rutas = resolver_rutas(directorio_datos)
    db = rutas['db']
    respaldos_dir = rutas['respaldos']
    respaldos_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(recursos() / 'backend'))
    from apps.core.respaldos import crear_copia, verificar_copia

    resultado = crear_copia(db, respaldos_dir, conservar=50)
    archivo_completo = respaldos_dir / resultado['archivo']
    verificar_copia(archivo_completo)
    resultado['archivo_completo'] = archivo_completo
    return resultado


def ensayar_migraciones_en_copia(directorio_datos):
    """Ensaya las migraciones pendientes EXCLUSIVAMENTE sobre una copia temporal en TEMP.

    Garantía: la base original NUNCA se modifica durante este ensayo.
    """
    rutas = resolver_rutas(directorio_datos)
    db_original = rutas['db']
    env_original = rutas['env']

    if not db_original.is_file() or not env_original.is_file():
        raise ValueError('No se puede ensayar migraciones sin base ni archivo de entorno.')

    temp_dir = tempfile.mkdtemp(prefix='Inventarios_ensayo_migracion_')
    temp_path = Path(temp_dir)
    try:
        # Copiar base y .env a la carpeta temporal aislada
        copia_db = temp_path / 'db.sqlite3'
        copia_env = temp_path / '.env'
        shutil.copy2(db_original, copia_db)
        shutil.copy2(env_original, copia_env)

        from dotenv import dotenv_values
        valores = dotenv_values(copia_env)
        clave = valores.get('SECRET_KEY', 'clave_temporal_para_ensayo_aislado_de_migraciones')

        # Configurar Django apuntando a la copia
        os.environ.update(
            ENV_FILE=str(copia_env),
            SECRET_KEY=clave,
            DATA_DIR=str(temp_path),
            DB_PATH=str(copia_db),
            BACKUP_DIR=str(temp_path / 'respaldos'),
            LOG_DIR=str(temp_path / 'logs'),
            DJANGO_SETTINGS_MODULE='config.settings.escritorio',
            DEBUG='False',
            ALLOWED_HOSTS='127.0.0.1,localhost',
            DESKTOP_RESOURCES=str(recursos())
        )
        sys.path.insert(0, str(recursos() / 'backend'))

        import django
        from django.conf import settings
        if settings.configured:
            settings.DATA_DIR = temp_path
            settings.DB_PATH = copia_db
            settings.DATABASES['default']['NAME'] = copia_db
            settings.LOG_DIR = temp_path / 'logs'
            (temp_path / 'logs').mkdir(parents=True, exist_ok=True)
            if hasattr(settings, 'LOGGING') and 'handlers' in settings.LOGGING and 'archivo' in settings.LOGGING['handlers']:
                settings.LOGGING['handlers']['archivo']['filename'] = temp_path / 'logs' / 'sistema.log'

        django.setup()
        from django.db import connection, connections
        from django.db.migrations.executor import MigrationExecutor
        from django.core.management import call_command

        ejecutor = MigrationExecutor(connection)
        plan = ejecutor.migration_plan(ejecutor.loader.graph.leaf_nodes())

        # Ejecutar migraciones en la copia
        call_command('migrate', interactive=False, verbosity=0)

        # Cerrar conexiones antes de verificar integridad física
        connections.close_all()

        # Comprobar integridad física y de claves foráneas de la copia migrada
        con = sqlite3.connect(copia_db.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            check_ok = con.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
            fk_ok = con.execute('PRAGMA foreign_key_check').fetchone() is None
            if not check_ok or not fk_ok:
                return {
                    'compatible': False,
                    'migraciones_pendientes': [str(m[0]) for m in plan],
                    'ensayo_exitoso': False,
                    'error': 'Fallo en comprobación de integridad o claves foráneas tras migrar la copia.'
                }
        finally:
            con.close()

        return {
            'compatible': True,
            'migraciones_pendientes': [str(m[0]) for m in plan],
            'ensayo_exitoso': True,
            'error': None
        }
    except Exception as exc:
        return {
            'compatible': False,
            'migraciones_pendientes': [],
            'ensayo_exitoso': False,
            'error': str(exc)
        }
    finally:
        try:
            from django.db import connections
            connections.close_all()
        except Exception:
            pass
        # Eliminar el directorio temporal del ensayo
        shutil.rmtree(temp_path, ignore_errors=True)


def planificar_actualizacion(directorio_datos, version_nueva, autorizar_migraciones=False):
    """Valida los prerrequisitos de actualización y prepara el respaldo verificable.

    Lanza:
        RuntimeError si hay procesos activos o si las migraciones fallan.
        ValueError si se intenta un downgrade.
    """
    info = detectar_instalacion_previa(directorio_datos)
    if not info['instalada']:
        raise ValueError('No se detectó una instalación previa para actualizar.')

    # 1. Comprobar downgrade
    verificar_compatibilidad_version(info['version'], version_nueva)

    # 2. Comprobar procesos activos
    activo, razon = detectar_procesos_activos(directorio_datos)
    if activo:
        raise RuntimeError(f'Actualización bloqueada: {razon}')

    # 3. Ensayar migraciones en copia
    ensayo = ensayar_migraciones_en_copia(directorio_datos)
    if not ensayo['ensayo_exitoso']:
        raise RuntimeError(f'Incompatibilidad de esquema detectada en el ensayo: {ensayo["error"]}')

    if ensayo['migraciones_pendientes'] and not autorizar_migraciones:
        raise RuntimeError(
            f'Se requieren {len(ensayo["migraciones_pendientes"])} migraciones pendientes. '
            'La actualización debe autorizarse explícitamente.'
        )

    # 4. Crear respaldo previo de seguridad verificado
    respaldo = crear_respaldo_seguridad(directorio_datos)

    return {
        'version_previa': info['version'],
        'version_nueva': version_nueva,
        'respaldo_previo': str(respaldo['archivo_completo']),
        'respaldo_sha256': respaldo['sha256'],
        'migraciones_pendientes': ensayo['migraciones_pendientes'],
        'preparada': True,
    }


def documentar_recuperacion_fallida(directorio_datos, ruta_respaldo):
    """Genera las instrucciones precisas para restaurar los datos si una actualización se interrumpe."""
    rutas = resolver_rutas(directorio_datos)
    db = rutas['db']
    respaldo = Path(ruta_respaldo)

    return (
        f'=== PROCEDIMIENTO DE RECUPERACIÓN / ROLLBACK ANTE FALLO DE ACTUALIZACIÓN ===\n'
        f'1. Asegúrese de que SistemaInventarios.exe no se esté ejecutando.\n'
        f'2. Respaldo verificado previo: {respaldo.resolve()}\n'
        f'3. Destino de la base de datos: {db.resolve()}\n'
        f'4. Para restaurar:\n'
        f'   copy /y "{respaldo.resolve()}" "{db.resolve()}"\n'
        f'5. Compruebe la integridad de la base restaurada antes de reabrir el sistema.\n'
        f'6. Ningún dato de configuración (.env) ni registros (logs) fueron eliminados.\n'
    )
