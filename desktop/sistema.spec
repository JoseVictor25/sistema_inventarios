# Construcción explícita: nunca recopilar backend/ completo como datos.
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

raiz = Path(SPECPATH).parent
sys.path[:0] = [str(raiz), str(raiz / 'backend')]
estaticos = Path(os.environ['INVENTARIOS_STATIC_BUILD'])
datos = [(str(raiz / 'frontend/templates'), 'frontend/templates'),
         (str(raiz / 'frontend/static'), 'frontend/static'),
         (str(estaticos), 'backend/staticfiles')]
datos += collect_data_files('tzdata') + collect_data_files('reportlab') + collect_data_files('webview')
ocultos = collect_submodules('apps') + collect_submodules('config') + collect_submodules('desktop')
ocultos = [m for m in ocultos if '.tests' not in m]
ocultos += ['django.db.backends.sqlite3', 'django.contrib.sessions.backends.db', 'webview.platforms.winforms']
ocultos += ['whitenoise.middleware', 'django.template.backends.django',
            'django.contrib.auth.backends', 'django.contrib.auth.password_validation',
            'django.contrib.messages.storage.fallback', 'django.contrib.sessions.serializers']
a = Analysis([str(raiz / 'desktop/launcher.py')], pathex=[str(raiz), str(raiz / 'backend')],
             binaries=[], datas=datos, hiddenimports=ocultos, excludes=['pytest', 'tkinter.test'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SistemaInventarios', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='SistemaInventarios')
