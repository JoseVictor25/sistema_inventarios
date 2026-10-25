"""Límite transaccional compartido por escrituras ordinarias de negocio."""
from functools import wraps

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError, transaction

from .exceptions import ErrorDeNegocio
from .permissions import tiene_permiso


def autorizar(usuario, permiso):
    """Exige permisos también al llamar un servicio sin una vista."""
    if not tiene_permiso(usuario, permiso):
        raise PermissionDenied("No tienes permiso para esta acción.")


def operacion(permiso):
    """Autoriza antes de escribir y traduce conflictos después del rollback."""
    def decorar(funcion):
        @wraps(funcion)
        def ejecutar(usuario, *args, **kwargs):
            autorizar(usuario, permiso)
            try:
                with transaction.atomic():
                    return funcion(usuario, *args, **kwargs)
            except ValidationError as error:
                raise ErrorDeNegocio(" ".join(error.messages)) from None
            except ObjectDoesNotExist:
                raise ErrorDeNegocio("El registro ya no existe. Actualiza la página.") from None
            except IntegrityError:
                raise ErrorDeNegocio("No se pudo guardar: revisa los nombres duplicados y las relaciones.") from None
            except OperationalError as error:
                if "locked" not in str(error).lower():
                    raise
                raise ErrorDeNegocio("Otro proceso está guardando datos. Actualiza la página e intenta nuevamente.") from None
        return ejecutar
    return decorar


def asignar_campos(objeto, datos, permitidos):
    """Rechaza campos ajenos al contrato, incluso desde llamadas directas."""
    if set(datos) - set(permitidos):
        raise ErrorDeNegocio("Se enviaron campos no permitidos.")
    for campo, valor in datos.items():
        setattr(objeto, campo, valor)
