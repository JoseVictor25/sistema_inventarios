"""Inicialización exclusiva; nunca migra una instalación existente."""
import os
import secrets
import sqlite3
import sys
from pathlib import Path
from .rutas import recursos, validar_temporal


def configurar(ruta, autorizar_nueva=False, solo_respaldo=False):
    destino = validar_temporal(ruta)
    destino.mkdir(parents=True, exist_ok=True)
    base, entorno = destino / 'db.sqlite3', destino / '.env'
    nueva = not base.exists() and not entorno.exists()
    if nueva and not autorizar_nueva:
        raise ValueError('Instalación nueva: requiere --inicializar.')
    if not nueva and (not base.is_file() or not entorno.is_file()):
        raise ValueError('Instalación incompleta: conserva los archivos y revisa la configuración.')
    if base.is_symlink() or entorno.is_symlink():
        raise ValueError('Archivos de instalación inseguros.')
    if any(p.exists() and p.stat().st_nlink > 1 for p in (base, entorno)):
        raise ValueError('No se permiten enlaces físicos para datos o configuración.')
    if nueva:
        with entorno.open('x', encoding='utf-8') as archivo:
            archivo.write('SECRET_KEY=' + secrets.token_urlsafe(64) + '\n')
        with base.open('xb'):
            pass
    from dotenv import dotenv_values
    valores = dotenv_values(entorno)
    clave = valores.get('SECRET_KEY')
    if not clave or len(clave) < 50:
        raise ValueError('La configuración necesita una SECRET_KEY válida; no se regeneró.')
    os.environ.update(ENV_FILE=str(entorno), SECRET_KEY=clave, DATA_DIR=str(destino),
        DB_PATH=str(base), BACKUP_DIR=str(destino / 'respaldos'), LOG_DIR=str(destino / 'logs'),
        DJANGO_SETTINGS_MODULE='config.settings.escritorio', DEBUG='False', ALLOWED_HOSTS='127.0.0.1,localhost',
        DESKTOP_RESOURCES=str(recursos()))
    sys.path.insert(0, str(recursos() / 'backend'))
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    if nueva:
        call_command('migrate', interactive=False, verbosity=0)
        call_command('cargar_datos_iniciales', verbosity=0)
    else:
        # Una consulta de esquema no autoriza a ejecutar migraciones.
        ejecutor = MigrationExecutor(connection)
        if ejecutor.migration_plan(ejecutor.loader.graph.leaf_nodes()) and not solo_respaldo:
            raise ValueError('Hay migraciones pendientes. Se requiere actualización autorizada sobre copia; no se migró esta base.')
    return destino
