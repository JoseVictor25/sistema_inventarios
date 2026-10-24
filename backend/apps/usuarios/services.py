"""Creación y edición controlada de usuarios de negocio."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.core.exceptions import ErrorDeNegocio
from apps.core.permissions import tiene_permiso
from .models import Usuario


def _autorizar(actor):
    if not tiene_permiso(actor, "gestionar_usuarios"):
        raise PermissionDenied("No tienes permiso para esta acción.")


def comprobar_usuario_editable(actor, usuario):
    """Protege cuentas al consultar y al guardar, independientemente del formulario."""
    _autorizar(actor)
    if usuario.is_superuser or usuario.pk == actor.pk:
        raise PermissionDenied("No puedes modificar esta cuenta desde la gestión ordinaria.")


def _guardar(usuario):
    """Valida y guarda; convierte duplicados concurrentes en un error visible."""
    try:
        with transaction.atomic():
            usuario.full_clean()
            usuario.save()
    except ValidationError:
        raise ErrorDeNegocio("Revisa los datos: el nombre de usuario debe ser válido y único.") from None
    except IntegrityError:
        raise ErrorDeNegocio("No se pudo guardar el usuario. Revisa el nombre y el rol seleccionado.") from None
    return usuario


def crear_usuario(actor, *, username, first_name, last_name, rol, is_active, password):
    """Crea una cuenta ordinaria con contraseña validada.

    Pasos:
        1. Comprobar autorización.
        2. Construir la cuenta sin privilegios técnicos y validar la contraseña.
        3. Guardar la cuenta validada.
    Lanza:
        PermissionDenied: actor sin permiso.
        ErrorDeNegocio: datos o contraseña inválidos.
    """
    # Paso 1: autorización independiente de la vista.
    _autorizar(actor)
    # Paso 2: campos explícitos; nunca aceptar is_staff/is_superuser del cliente.
    usuario = Usuario(username=username, first_name=first_name, last_name=last_name,
                      rol=rol, is_active=is_active)
    try:
        validate_password(password, usuario)
    except ValidationError as error:
        raise ErrorDeNegocio(" ".join(error.messages), "password2") from None
    usuario.set_password(password)
    # Paso 3: validación y persistencia atómica.
    return _guardar(usuario)


@transaction.atomic
def editar_usuario(actor, usuario_id, *, username, first_name, last_name, rol, is_active):
    """Edita campos ordinarios conservando contraseña y privilegios técnicos.

    Pasos:
        1. Consultar de nuevo la cuenta y comprobar protección/autorización.
        2. Asignar exclusivamente los campos permitidos.
        3. Validar y guardar.
    Lanza:
        PermissionDenied: actor no autorizado, cuenta propia o superusuario.
        ErrorDeNegocio: datos inválidos o cuenta ya inexistente.
    """
    # Paso 1: no confiar en una instancia modificada por el formulario.
    _autorizar(actor)
    try:
        usuario = Usuario.objects.select_for_update().get(pk=usuario_id)
    except Usuario.DoesNotExist:
        raise ErrorDeNegocio("El usuario ya no existe.") from None
    comprobar_usuario_editable(actor, usuario)
    # Paso 2: la contraseña y los privilegios no forman parte de esta operación.
    usuario.username = username
    usuario.first_name = first_name
    usuario.last_name = last_name
    usuario.rol = rol
    usuario.is_active = is_active
    # Paso 3: validar antes de guardar.
    return _guardar(usuario)
