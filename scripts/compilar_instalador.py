"""Inspecciona onedir y compila B3 bloqueado, exclusivamente en una salida TEMP nueva."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

RAIZ = Path(__file__).resolve().parent.parent
PRIVADOS = {'reporte_migraciones_fase1.md', 'solucion_error_terminal.md'}
PROTEGIDOS = ['backend/datos/db.sqlite3', 'backend/.env',
              'backend/REPORTE_MIGRACIONES_FASE1.md', 'backend/SOLUCION_ERROR_TERMINAL.md']


def sha(ruta):
    with ruta.open('rb') as archivo:
        return hashlib.file_digest(archivo, 'sha256').hexdigest()


def inspeccionar(paquete):
    paquete = Path(paquete).absolute()
    for padre in (paquete, *paquete.parents):
        if padre.is_symlink() or padre.is_junction():
            raise ValueError('No se admiten enlaces de directorio.')
    if not (paquete / 'SistemaInventarios.exe').is_file() or not (paquete / '_internal').is_dir():
        raise ValueError('Se requiere onedir completo con EXE y _internal.')
    archivos = []
    for ruta in sorted(paquete.rglob('*')):
        if ruta.is_symlink() or ruta.is_junction():
            raise ValueError('Enlace rechazado: ' + ruta.name)
        if not ruta.is_file():
            continue
        relativa = ruta.relative_to(paquete)
        partes = [p.lower() for p in relativa.parts]
        nombre = ruta.name.lower()
        if (ruta.stat().st_nlink > 1 or any(c in str(relativa) for c in '\r\n";')
                or nombre in PRIVADOS or nombre.startswith('.env')
                or any(p in {'.git', 'datos', 'respaldos', 'backups', 'logs', 'venv'} for p in partes)
                or any(x in nombre for x in ('.sqlite', '.db', '.log', '.backup', '.bak'))):
            raise ValueError('Archivo no distribuible: ' + str(relativa))
        archivos.append((ruta, relativa, sha(ruta)))
    return archivos


def buscar_iscc():
    candidatos = [
        shutil.which('ISCC.exe'),
        'E:/Inno Setup 7/ISCC.exe',
        'C:/Program Files/Inno Setup 7/ISCC.exe',
        'C:/Program Files (x86)/Inno Setup 7/ISCC.exe',
    ]
    for variable in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
        base = os.environ.get(variable)
        if base:
            candidatos += [
                str(Path(base) / 'Inno Setup 7/ISCC.exe'),
                str(Path(base) / 'Inno Setup 6/ISCC.exe'),
                str(Path(base) / 'Programs/Inno Setup 7/ISCC.exe'),
                str(Path(base) / 'Programs/Inno Setup 6/ISCC.exe'),
            ]
    return next((Path(p) for p in candidatos if p and Path(p).is_file()), None)


def preparar(paquete, salida):
    archivos = inspeccionar(paquete)
    entradas, manifiesto = [], []
    for origen, relativa, huella in archivos:
        destino = salida / 'payload' / relativa
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, destino)
        if sha(destino) != huella:
            raise ValueError('El paquete cambió durante la copia.')
        subdir = str(relativa.parent)
        carpeta = '{app}' + ('\\' + subdir if subdir != '.' else '')
        entradas.append(f'Source: "{destino}"; DestDir: "{carpeta}"; Flags: ignoreversion')
        manifiesto.append(dict(archivo=str(relativa), sha256=huella, bytes=destino.stat().st_size))
    (salida / 'archivos.iss').write_text('\n'.join(entradas), encoding='utf-8-sig')
    (salida / 'contenido.json').write_text(json.dumps(manifiesto, indent=2), encoding='utf-8')
    return manifiesto


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paquete', required=True, type=Path)
    parser.add_argument('--solo-verificar', action='store_true')
    parser.add_argument('--iscc', type=Path, help='Compilador Inno Setup previamente instalado por el operador.')
    args = parser.parse_args()
    if Path(sys.executable).resolve() != RAIZ / 'venv/Scripts/python.exe':
        parser.error('Utiliza venv/Scripts/python.exe.')
    antes = {p: sha(RAIZ / p) for p in PROTEGIDOS}
    salida = Path(tempfile.mkdtemp(prefix='Inventarios_instalador_B3_'))
    print('Evidencias y salida:', salida, flush=True)
    try:
        contenido = preparar(args.paquete, salida)
        print('Archivos inspeccionados:', len(contenido))
        if args.solo_verificar:
            return 0
        iscc = args.iscc or buscar_iscc()
        if not iscc or not iscc.is_file():
            print('ISCC.exe no encontrado. Consulta desktop/installer/README.md. No se instaló software.')
            return 2
        comando = [str(iscc.resolve()), '/DVerifiedFiles=' + str(salida / 'archivos.iss'),
                   '/DBuildOutput=' + str(salida / 'salida'), str(RAIZ / 'desktop/installer/setup.iss')]
        with (salida / 'compilacion.txt').open('w', encoding='utf-8') as log:
            resultado = subprocess.run(comando, stdout=log, stderr=subprocess.STDOUT)
        if resultado.returncode:
            print('Error en compilación de Inno Setup (código %s). Revise %s' % (resultado.returncode, salida / 'compilacion.txt'))
            return resultado.returncode
        for exe in (salida / 'salida').glob('*.exe'):
            print('Instalador BLOQUEADO B3, no ejecutado:', exe, 'SHA-256:', sha(exe))
        return 0
    finally:
        if antes != {p: sha(RAIZ / p) for p in PROTEGIDOS}:
            raise RuntimeError('Cambió un archivo protegido.')
        print('Archivos protegidos intactos.')


if __name__ == '__main__':
    sys.exit(main())
