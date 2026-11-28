"""Ejecuta pruebas Django seleccionadas con SQLite y DATA_DIR temporales."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from verificar_catalogo_fase3 import preparar_entorno


def main():
    raiz = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='Inventarios_pruebas_frontend_') as temporal:
        env = preparar_entorno(Path(temporal))
        etiquetas = sys.argv[1:] or ['apps.ventas.tests.test_historial_frontend',
                                     'apps.ventas.tests.test_menu_frontend',
                                     'apps.core.tests.test_frontend_static',
                                     'apps.core.tests.test_paginacion_frontend']
        return subprocess.run([sys.executable, str(raiz / 'backend/manage.py'), 'test',
                               *etiquetas, '--noinput'], env=env, cwd=raiz / 'backend').returncode


if __name__ == '__main__':
    sys.exit(main())
