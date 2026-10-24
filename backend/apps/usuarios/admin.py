"""Admin de usuarios: Usuario, Rol y Permiso."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Permiso, Rol, Usuario


@admin.register(Permiso)
class PermisoAdmin(admin.ModelAdmin):
    list_display = ["codigo", "descripcion"]
    search_fields = ["codigo", "descripcion"]
    ordering = ["codigo"]


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ["nombre", "descripcion"]
    search_fields = ["nombre"]
    filter_horizontal = ["permisos"]


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ["username", "first_name", "last_name", "rol", "is_active", "is_staff"]
    list_filter = ["rol", "is_active", "is_staff"]
    fieldsets = UserAdmin.fieldsets + (
        ("Rol de negocio", {"fields": ("rol",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Rol de negocio", {"fields": ("rol",)}),
    )
