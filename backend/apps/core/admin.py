"""Protección del historial en el administrador técnico."""


class SoloLecturaAdminMixin:
    """Consulta sin altas, cambios ni borrados, incluso con POST directo.

    Las escrituras corresponden a los servicios transaccionales del dominio.
    Se conservan los permisos de consulta normales de Django.
    """

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [campo.name for campo in self.model._meta.fields]
