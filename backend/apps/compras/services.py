"""Gestión de proveedores; registrar compras corresponde a fase 4."""
from apps.core.operaciones import asignar_campos, operacion
from apps.core.utils import asignar_auditoria
from .models import Proveedor

CAMPOS_PROVEEDOR = ("nombre", "tipo", "contacto", "telefono", "origen", "activo")


@operacion("gestionar_compras")
def guardar_proveedor(usuario, datos, proveedor_id=None):
    """Crea o edita datos comerciales, sin borrar compras.

    Pasos:
        1. Recuperar proveedor y asignar campos permitidos.
        2. Validar, asignar autoría y guardar.
    Lanza:
        ErrorDeNegocio: nombre duplicado, tipo inválido o registro inexistente.
    """
    # Paso 1: no se aceptan campos de auditoría desde el cliente.
    proveedor = Proveedor.objects.get(pk=proveedor_id) if proveedor_id else Proveedor()
    asignar_campos(proveedor, datos, CAMPOS_PROVEEDOR)
    # Paso 2: la transacción del decorador mantiene el registro intacto si falla.
    asignar_auditoria(proveedor, usuario)
    proveedor.full_clean()
    proveedor.save()
    return proveedor
