"""Construcción onedir en TEMP, sin configuración del negocio."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from verificar_catalogo_fase3 import preparar_entorno

RAIZ = Path(__file__).resolve().parent.parent


def main():
    if Path(sys.executable).resolve() != RAIZ / 'venv/Scripts/python.exe':
        raise RuntimeError('Usa exclusivamente el Python del venv.')
    temporal = Path(tempfile.mkdtemp(prefix='Inventarios_build_fase10_'))
    env = preparar_entorno(temporal)
    env.update(PYINSTALLER_CONFIG_DIR=str(temporal / 'cache_pyinstaller'), PYTHONDONTWRITEBYTECODE='1')
    modulo = temporal / 'settings_fase3.py'
    with modulo.open('a', encoding='utf-8') as archivo:
        archivo.write(f"\nSTATIC_ROOT = {str(temporal / 'staticfiles')!r}\n")
    subprocess.run([sys.executable, str(RAIZ / 'backend/manage.py'), 'collectstatic', '--noinput'], env=env, check=True)
    env['INVENTARIOS_STATIC_BUILD'] = str(temporal / 'staticfiles')
    subprocess.run([sys.executable, '-m', 'PyInstaller', str(RAIZ / 'desktop/sistema.spec'),
                    '--distpath', str(temporal / 'dist'), '--workpath', str(temporal / 'work'), '--noconfirm', '--clean'],
                   cwd=RAIZ, env=env, check=True)
    print('Paquete experimental:', temporal / 'dist/SistemaInventarios')


if __name__ == '__main__':
    main()
