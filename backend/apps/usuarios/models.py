"""Modelos de usuarios, roles y permisos de negocio.

Diagrama de dependencias (§7.10):
    Permiso  ←──(M2M)──  Rol  ←──(FK)──  Usuario(AbstractUser)
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class Permiso(models.Model):
    """Permiso de negocio identificado por un código único (§10)."""

    codigo = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=200)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "permiso"
        verbose_name_plural = "permisos"

    def __str__(self):
        return self.codigo


class Rol(models.Model):
    """Rol de usuario: conjunto de permisos de negocio."""

    nombre = models.CharField(max_length=60, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)
    permisos = models.ManyToManyField(
        Permiso,
        blank=True,
        related_name="roles",
    )

    class Meta:
        ordering = ["nombre"]
        verbose_name = "rol"
        verbose_name_plural = "roles"

    def __str__(self):
        return self.nombre


class Usuario(AbstractUser):
    """Usuario personalizado con rol de negocio (§7 — usuarios).

    Hereda username, password, first_name, last_name e is_active de
    AbstractUser. No se agregan campos 'nombre' ni 'activo' (§7.10).
    El campo 'rol' es opcional: los superusuarios funcionan sin rol.
    """

    rol = models.ForeignKey(
        "usuarios.Rol",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="usuarios",
        help_text="Rol de negocio del usuario. Vacío en superusuarios.",
    )

    class Meta(AbstractUser.Meta):
        ordering = ["username"]
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.username
