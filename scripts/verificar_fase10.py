"""Verificación del Bloque A; todas las escrituras se confinan a TEMP."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from verificar_catalogo_fase3 import preparar_entorno
from verificar_reportes_fase8 import huellas, RAIZ


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pruebas', action='store_true')
    parser.add_argument('--http', action='store_true')
    parser.add_argument('--abrir', action='store_true')
    parser.add_argument('--escritorio', action='store_true')
    parser.add_argument('--paquete', type=Path, help='Carpeta onedir experimental dentro de TEMP.')
    args = parser.parse_args()
    if Path(sys.executable).resolve() != RAIZ / 'venv/Scripts/python.exe':
        parser.error('Usa el Python del venv.')
    antes = huellas()
    temporal = Path(tempfile.mkdtemp(prefix='Inventarios_fase10_'))
    print('Evidencias:', temporal, flush=True)
    env = preparar_entorno(temporal)
    resultados = {}
    try:
        if args.paquete:
            sys.path.insert(0, str(RAIZ))
            from desktop.rutas import validar_temporal
            paquete = validar_temporal(args.paquete)
            prohibidos = {'.env', 'REPORTE_MIGRACIONES_FASE1.md', 'SOLUCION_ERROR_TERMINAL.md'}
            archivos = [p for p in paquete.rglob('*') if p.is_file()]
            assert archivos, 'El paquete está vacío.'
            assert not any(p.name in prohibidos or p.suffix in ('.sqlite3', '.sqlite', '.db', '.log') for p in archivos), 'El paquete contiene archivos privados o de datos.'
            ejecutable = paquete / 'SistemaInventarios.exe'
            for nombre, opciones in [('nuevo', ['--inicializar', '--diagnostico']), ('existente', ['--diagnostico']), ('respaldo', ['--respaldo'])]:
                with (temporal / ('paquete_' + nombre + '.txt')).open('w', encoding='utf-8') as salida:
                    proceso = subprocess.run([str(ejecutable), '--datos-temporales', str(temporal / 'instalacion_paquete'), *opciones], stdout=salida, stderr=subprocess.STDOUT, timeout=120)
                resultados['paquete_' + nombre] = proceso.returncode
                if proceso.returncode:
                    break
            resultados['paquete_archivos'] = 0
            print('Archivos inspeccionados:', len(archivos), 'bytes:', sum(p.stat().st_size for p in archivos), flush=True)
        if args.escritorio:
            for numero in (1, 2):
                r = subprocess.run([sys.executable, str(RAIZ / 'scripts/prueba_desktop_fase10.py'), str(temporal / 'instalacion')])
                resultados['escritorio_' + str(numero)] = r.returncode
                if r.returncode:
                    break
        if args.pruebas:
            for nombre, comando in [('check', ['check']), ('migraciones', ['makemigrations', '--check', '--dry-run']), ('test', ['test', '--noinput'])]:
                with (temporal / (nombre + '.txt')).open('w', encoding='utf-8') as salida:
                    r = subprocess.run([sys.executable, str(RAIZ / 'backend/manage.py'), *comando], env=env, cwd=RAIZ / 'backend', stdout=salida, stderr=subprocess.STDOUT)
                resultados[nombre] = r.returncode
                print(nombre, r.returncode, flush=True)
        if args.http:
            # Reutiliza el recorrido probado de reportes, exportaciones y permisos.
            r = subprocess.run([sys.executable, str(RAIZ / 'scripts/verificar_reportes_fase8.py'), '--http'])
            resultados['http_reportes'] = r.returncode
            r = subprocess.run([sys.executable, str(RAIZ / 'scripts/verificar_fase9.py'), '--http', '--respaldos'])
            resultados['http_respaldos'] = r.returncode
        if args.abrir:
            resultados['launcher'] = subprocess.run([sys.executable, str(RAIZ / 'desktop/launcher.py'),
                '--datos-temporales', str(temporal / 'instalacion'), '--inicializar']).returncode
    finally:
        resultados['protegidos_intactos'] = antes == huellas()
        (temporal / 'resultados.json').write_text(json.dumps(resultados, indent=2), encoding='utf-8')
        print(resultados, flush=True)
    return int(not resultados.pop('protegidos_intactos') or any(resultados.values()))


if __name__ == '__main__':
    sys.exit(main())
