"""Bloqueo de exclusión de instancia activa (servidor HTTP incluido).

Un único archivo `.instancia.lock` en el directorio de datos coordina
entre instalador, herramienta de mantenimiento y proceso de la aplicación.

Garantías:
- El bloqueo se toma ANTES de iniciar el servidor HTTP y se libera al cerrar.
- `detectar_instancia_activa()` distingue entre: sin lock, lock libre (no hay
  instancia) y lock retenido (instancia activa o proceso de mantenimiento).
- No se fuerza el cierre de ningún proceso; solo se informa del estado.
- Compatible con los tests: acepta una ruta temporal aislada.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import sys


NOMBRE_LOCK = '.instancia.lock'


def ruta_lock(directorio_datos: Path) -> Path:
    return Path(directorio_datos) / NOMBRE_LOCK


@contextmanager
def bloqueo_instancia(directorio_datos: Path):
    """Context manager: toma el bloqueo de exclusión de instancia activa.

    Levanta:
        OSError: si ya existe una instancia activa (lock retenido).
    """
    archivo = ruta_lock(directorio_datos)
    if archivo.is_symlink():
        raise OSError('El archivo de control de instancia no es seguro (enlace simbólico).')

    manejador = archivo.open('a+b')
    tomado = False
    try:
        manejador.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(manejador.fileno(), msvcrt.LK_NBLCK, 1)
                tomado = True
            except OSError:
                manejador.close()
                raise OSError(
                    'Ya existe una instancia activa del Sistema de Inventarios. '
                    'Ciérrala antes de realizar operaciones de mantenimiento.'
                ) from None
        else:
            import fcntl
            try:
                fcntl.flock(manejador.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                tomado = True
            except OSError:
                manejador.close()
                raise OSError('Ya existe una instancia activa.') from None

        yield manejador
    finally:
        if tomado:
            manejador.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(manejador.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(manejador.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        manejador.close()


def detectar_instancia_activa(directorio_datos: Path) -> tuple[bool, str]:
    """Comprueba si hay una instancia de la aplicación (o el servidor HTTP) activa.

    Devuelve:
        (False, mensaje) si no hay instancia activa.
        (True, mensaje)  si el lock está retenido por otro proceso.

    Esta función detecta:
    - El proceso principal de la aplicación (que toma el lock en launcher.py).
    - El servidor HTTP Waitress (iniciado dentro del mismo proceso).
    - Cualquier proceso de mantenimiento que use bloqueo_instancia().

    Limitación conocida (B3): no detecta el nombre exacto del ejecutable
    (SistemaInventarios.exe) en Windows sin psutil o WMI; la detección se
    basa exclusivamente en el cerrojo de archivo.
    """
    archivo = ruta_lock(directorio_datos)

    if not archivo.exists():
        return False, 'Sin instancia activa (sin archivo de control).'

    if archivo.is_symlink():
        return True, 'El archivo de control de instancia es un enlace simbólico (inseguro).'

    try:
        manejador = archivo.open('a+b')
    except OSError as exc:
        return True, f'El archivo de control está retenido por otro proceso: {exc}'

    try:
        manejador.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(manejador.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(manejador.fileno(), msvcrt.LK_UNLCK, 1)
                return False, 'Sin instancia activa.'
            except OSError:
                return True, (
                    'La aplicación SistemaInventarios o el servidor HTTP está en ejecución. '
                    'Ciérrala antes de actualizar.'
                )
        else:
            import fcntl
            try:
                fcntl.flock(manejador.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(manejador.fileno(), fcntl.LOCK_UN)
                return False, 'Sin instancia activa.'
            except OSError:
                return True, 'Proceso activo detectado.'
    finally:
        manejador.close()
