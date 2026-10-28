"""Respaldo para el operador local; no instala tareas ni aplica migraciones.

Uso: venv/Scripts/python.exe scripts/respaldo.py [carpeta_destino] [conservar]
Sin argumentos utiliza la configuración Django. No ejecutarlo sobre datos reales
durante desarrollo: el verificador de fase 9 suministra configuración temporal.
"""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    raiz = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('carpeta_destino', nargs='?')
    parser.add_argument('conservar', nargs='?', type=int)
    args = parser.parse_args()
    if Path(sys.executable).resolve() != (raiz / 'venv/Scripts/python.exe').resolve():
        parser.error('Utiliza venv/Scripts/python.exe.')
    sys.path.insert(0, str(raiz / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.produccion')
    import django
    django.setup()
    from django.conf import settings
    from apps.core.respaldos import crear_copia, ErrorRespaldo
    try:
        if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
            raise ErrorRespaldo('El respaldo disponible requiere SQLite.')
        resultado = crear_copia(settings.DATABASES['default']['NAME'],
            args.carpeta_destino or settings.BACKUP_DIR,
            args.conservar if args.conservar is not None else settings.BACKUP_CONSERVAR)
    except ErrorRespaldo as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
