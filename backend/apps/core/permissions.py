"""Autorización mediante los permisos de negocio del rol (§10)."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def tiene_permiso(usuario, codigo):
    """Deniega por defecto; conserva la excepción del superusuario activo."""
    if not usuario.is_authenticated or not usuario.is_active:
        return False
    if usuario.is_superuser:
        return True
    if not getattr(usuario, "rol_id", None):
        return False
    return usuario.rol.permisos.filter(codigo=codigo).exists()


def codigos_permitidos(usuario):
    """Lista códigos efectivos sin guardarlos en la sesión ni modificar datos."""
    if not usuario.is_authenticated or not usuario.is_active:
        return []
    if usuario.is_superuser:
        from apps.usuarios.models import Permiso
        return list(Permiso.objects.values_list("codigo", flat=True))
    if not getattr(usuario, "rol_id", None):
        return []
    return list(usuario.rol.permisos.values_list("codigo", flat=True))


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
