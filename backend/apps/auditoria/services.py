"""Registro interno de cambios; la autorización corresponde al servicio invocante."""
from .models import LogAuditoria


def registrar_cambio(usuario, accion, entidad, entidad_id, anterior, nuevo):
    """Registra valores serializables en la transacción del servicio invocante.

    Pasos:
        1. Construir y validar la entrada con su autor.
        2. Guardar y devolver el registro inmutable.
    Lanza:
        ValidationError: entrada inválida; el servicio revierte la operación.
    """
    # Paso 1: no recibe datos de request ni expone una ruta de escritura.
    entrada = LogAuditoria(usuario=usuario, accion=accion, entidad=entidad,
                           entidad_id=entidad_id, valor_anterior=anterior, valor_nuevo=nuevo)
    entrada.full_clean()
    # Paso 2: la transacción externa incluye el precio y esta entrada.
    entrada.save()
    return entrada
