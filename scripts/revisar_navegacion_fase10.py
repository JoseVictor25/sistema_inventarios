"""Demostración aislada en el launcher, con roles y bitácora ficticios."""
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

RAIZ = Path(__file__).resolve().parent.parent


def main():
    if Path(sys.executable).resolve() != RAIZ / 'venv/Scripts/python.exe':
        raise RuntimeError('Utiliza el Python del venv.')
    sys.path.insert(0, str(RAIZ))
    from desktop.inicializacion import configurar
    from verificar_reportes_fase8 import huellas
    antes = huellas()
    ruta = Path(tempfile.mkdtemp(prefix='Inventarios_revision_navegacion_'))
    try:
        configurar(ruta, autorizar_nueva=True)
        from apps.reportes.tests.datos import crear_datos
        from apps.catalogo.services import cambiar_precio
        from decimal import Decimal
        from django.db import connections
        clave = secrets.token_urlsafe(20)
        datos = crear_datos(clave)
        cambiar_precio(datos['dueno'], datos['unidad'], Decimal('50'))
        cambiar_precio(datos['dueno'], datos['unidad'], Decimal('60'))
        connections.close_all()
        print('Instalación ficticia:', ruta, flush=True)
        print('Usuarios: dueno_fase8 / vendedor_fase8. Contraseña temporal:', clave, flush=True)
        print('Revisar Inicio y Bitácora a 390, 768, 1024, 1280, 1366, 1600 y 1920 px.', flush=True)
        return subprocess.run([sys.executable, str(RAIZ / 'desktop/launcher.py'), '--datos-temporales', str(ruta)]).returncode
    finally:
        assert antes == huellas(), 'Cambió un archivo protegido.'


if __name__ == '__main__':
    sys.exit(main())
