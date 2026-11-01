"""Separación de recursos y datos. Bloque A: solo instalaciones temporales."""
import os
from pathlib import Path
import tempfile


def recursos():
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
