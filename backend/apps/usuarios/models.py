from django.contrib.auth.models import AbstractUser


class Usuario(AbstractUser):
    """Usuario personalizado. Se define desde el inicio del proyecto para
    poder agregar el Rol y otros campos después sin romper las migraciones.
    TODO: relacionar con Rol (clase Rol y Permiso del diagrama)."""
