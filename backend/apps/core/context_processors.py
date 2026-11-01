from pathlib import Path
import hashlib
from functools import lru_cache


@lru_cache(maxsize=32)
def _version(ruta, fecha, tamano):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()[:16]


def version_recurso(nombre):
    base = settings.FRONTEND_DIR / 'static' if settings.DEBUG else Path(settings.STATIC_ROOT)
    ruta = base / nombre
    if not ruta.is_file():
        return 'ausente'
    estado = ruta.stat()
    return _version(str(ruta), estado.st_mtime_ns, estado.st_size)

from django.conf import settings

from .frontend import RECURSOS_APP, RECURSOS_VENDOR
from .permissions import codigos_permitidos


def _estaticos_listos(recursos):
    """Comprueba la fuente en desarrollo y STATIC_ROOT en producción."""
    base = settings.FRONTEND_DIR / "static" if settings.DEBUG else Path(settings.STATIC_ROOT)
    return all((base / ruta).is_file() for ruta in recursos)


def datos_del_negocio(request):
    """Pone en todas las plantillas: {{ NOMBRE_NEGOCIO }} y {{ MONEDA_SIMBOLO }}."""
    return {
        "version_css": version_recurso('css/app.css'),
        "version_js": version_recurso('js/app.js'),
        "permisos": codigos_permitidos(request.user),
        "NOMBRE_NEGOCIO": settings.NOMBRE_NEGOCIO,
        "MONEDA_SIMBOLO": settings.MONEDA_SIMBOLO,
        "recursos_frontend_listos": _estaticos_listos(RECURSOS_VENDOR),
        "recursos_app_listos": _estaticos_listos(RECURSOS_APP),
    }
