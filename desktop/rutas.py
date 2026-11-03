"""Separación de recursos y datos persistentes.

Bloque A: modo temporal experimental.
Bloque B3: modo instalado persistente con ProgramData y Program Files.
"""
import os
from pathlib import Path
import tempfile

PROGRAM_FILES_DIR = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'SistemaInventarios'
PROGRAM_DATA_DIR = Path(os.environ.get('ProgramData', 'C:/ProgramData')) / 'SistemaInventarios'


def recursos():
    """Ruta base de recursos de la aplicación (código, plantillas, estáticos)."""
    return Path(__file__).resolve().parent.parent


def validar_temporal(ruta):
    """Rechaza rutas implícitas, enlaces y destinos fuera de TEMP antes de escribir."""
    original = Path(ruta)
    if not original.is_absolute():
        raise ValueError('Indica una ruta temporal absoluta.')
    destino = original.resolve()
    temporal = Path(tempfile.gettempdir()).resolve()
    protegida = Path(os.environ.get('ProgramData', 'C:/ProgramData')).resolve()
    if destino == temporal or not destino.is_relative_to(temporal) or destino.is_relative_to(protegida) or destino.is_relative_to(recursos()):
        raise ValueError('El Bloque A solo permite una subcarpeta independiente de TEMP.')
    for parte in (original, *original.parents):
        if parte.is_symlink() or (hasattr(parte, 'is_junction') and parte.is_junction()):
            raise ValueError('No se permiten enlaces ni redirecciones de directorio.')
    return destino


def validar_datos_instalados(ruta=None):
    """Valida y resuelve la ruta de datos persistentes del modo instalado.

    Rechaza:
    - Rutas relativas.
    - Rutas dentro de Program Files (los datos nunca van con el ejecutable).
    - Rutas dentro del árbol de recursos/código del sistema.
    - Raíces de unidad o de ProgramData directamente sin subdirectorio.
    - Enlaces simbólicos, uniones de directorio (junctions) y redirecciones.
    """
    if ruta is None:
        ruta = os.environ.get('INVENTARIOS_DATOS_INSTALADOS') or PROGRAM_DATA_DIR
    original = Path(ruta)
    if not original.is_absolute():
        raise ValueError('Indica una ruta absoluta para los datos instalados.')
    destino = original.resolve()

    # Rechazar si coincide con la raíz de unidad
    if destino == destino.parent:
        raise ValueError('La ruta de datos no puede ser la raíz de una unidad.')

    # Rechazar Program Files
    for var in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
        base = os.environ.get(var)
        if base:
            pf_path = Path(base).resolve()
            if destino == pf_path or destino.is_relative_to(pf_path):
                raise ValueError('Nunca escribir información del negocio dentro de Program Files.')

    # Rechazar recursos de la aplicación
    rec = recursos()
    if destino == rec or destino.is_relative_to(rec):
        raise ValueError('Los datos no pueden ubicarse dentro de los archivos del programa o repositorio.')

    # Rechazar raíz de ProgramData directamente
    for var in ('ProgramData',):
        base = os.environ.get(var, 'C:/ProgramData')
        if base and destino == Path(base).resolve():
            raise ValueError('La ruta de datos debe ser una subcarpeta dedicada, no la raíz de ProgramData.')

    # Rechazar enlaces simbólicos o junctions en cualquier punto
    for parte in (original, *original.parents):
        if parte.is_symlink() or (hasattr(parte, 'is_junction') and parte.is_junction()):
            raise ValueError('No se permiten enlaces ni redirecciones de directorio en datos instalados.')

    return destino


def resolver_rutas(directorio_datos):
    """Estructura canónica de archivos persistentes en el directorio de datos."""
    directorio = Path(directorio_datos)
    return {
        'datos': directorio,
        'db': directorio / 'db.sqlite3',
        'env': directorio / '.env',
        'respaldos': directorio / 'respaldos',
        'logs': directorio / 'logs',
        'operador': directorio / 'operador.json',
        'lock': directorio / '.respaldos.lock',
    }


def obtener_ruta_datos(args=None):
    """Determina si la ejecución es experimental (temporal) o instalada persistente."""
    if args and getattr(args, 'datos_temporales', None):
        return 'temporal', validar_temporal(args.datos_temporales)
    ruta_instalada = getattr(args, 'datos_instalados', None) if args else None
    return 'instalado', validar_datos_instalados(ruta_instalada)
