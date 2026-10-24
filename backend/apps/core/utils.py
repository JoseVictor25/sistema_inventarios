"""Utilidades compartidas por todos los servicios del backend."""


def asignar_auditoria(instancia, usuario):
    """Asigna creado_por / modificado_por según el estado de la instancia.

    Pasos:
        1. Si la instancia no tiene clave primaria (es nueva), asigna ``creado_por``.
        2. Siempre asigna ``modificado_por``.

    Usar antes de ``instancia.save()`` dentro del servicio correspondiente.
    No depende de middleware: el usuario lo recibe el servicio como parámetro.
    """
    if instancia.pk is None:
        instancia.creado_por = usuario
    instancia.modificado_por = usuario
