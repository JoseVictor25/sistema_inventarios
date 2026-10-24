from django.conf import settings

from .frontend import RECURSOS_FRONTEND
from .permissions import codigos_permitidos


def datos_del_negocio(request):
    """Pone en todas las plantillas: {{ NOMBRE_NEGOCIO }} y {{ MONEDA_SIMBOLO }}."""
    return {
        "permisos": codigos_permitidos(request.user),
        "NOMBRE_NEGOCIO": settings.NOMBRE_NEGOCIO,
        "MONEDA_SIMBOLO": settings.MONEDA_SIMBOLO,
        "recursos_frontend_listos": all(
            (settings.FRONTEND_DIR / "static" / ruta).is_file()
            for ruta in RECURSOS_FRONTEND
        ),
    }
