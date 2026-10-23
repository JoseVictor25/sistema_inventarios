"""Base de autorización. No crea roles ni tablas de la fase 1."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def tiene_permiso(usuario, codigo):
    """Deniega por defecto; la integración de roles corresponde a la fase 2."""
    return bool(usuario.is_authenticated and usuario.is_active and usuario.is_superuser)


def permiso_requerido(codigo):
    """Exige sesión y permiso; conserva el acceso del superusuario."""
    def decorar(vista):
        @login_required
        @wraps(vista)
        def protegida(request, *args, **kwargs):
            if not tiene_permiso(request.user, codigo):
                raise PermissionDenied("No tienes permiso para esta acción.")
            return vista(request, *args, **kwargs)
        return protegida
    return decorar
