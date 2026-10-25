"""Lógica de negocio de inventario. Las vistas llaman a estas funciones;
así la lógica se prueba fácil y no se duplica."""
from django.db import OperationalError
from django.db.models import F
from django.utils import timezone

from apps.core.exceptions import ErrorDeNegocio
from .models import Lote


def descontar_stock_fefo(producto, unidades):
    """Descuenta `unidades` del producto, empezando por el lote que vence primero.

    Pasos:
        1. Validar que `unidades` sea un entero mayor que cero.
        2. Bloquear los lotes con stock y no vencidos (evita que dos ventas
           simultáneas tomen las mismas unidades).
        3. Comprobar que el stock total alcance.
        4. Recorrer los lotes por fecha de vencimiento y descontar de cada uno.
        5. Devolver de qué lote salió cada cantidad (para calcular costo y ganancia).

    Lanza:
        ErrorDeNegocio: si las unidades no son válidas o el stock no alcanza.

    Debe llamarse dentro de `transaction.atomic()`.
    """
    # Paso 1: validar la entrada
    if not isinstance(unidades, int) or isinstance(unidades, bool) or unidades <= 0:
        raise ErrorDeNegocio("La cantidad a descontar debe ser un número entero mayor que cero.")

    # Paso 2: lotes disponibles, el que vence antes primero (RN-06 y RN-07)
    try:
        lotes = list(
            Lote.objects.select_for_update()
            .filter(producto=producto, cantidad_actual__gt=0)
            .exclude(fecha_vencimiento__lt=timezone.localdate())
            .order_by(F("fecha_vencimiento").asc(nulls_last=True), "id")
        )

        # Paso 3: comprobar el stock
        disponible = sum(lote.cantidad_actual for lote in lotes)
        if disponible < unidades:
            raise ErrorDeNegocio(
                f"No alcanza el stock de {producto.nombre}: quedan {disponible} unidades."
            )

        # Paso 4: descontar lote por lote
        restante = unidades
        salidas = []
        for lote in lotes:
            tomar = min(lote.cantidad_actual, restante)
            lote.cantidad_actual -= tomar
            lote.save(update_fields=["cantidad_actual"])
            salidas.append((lote, tomar))
            restante -= tomar
            if restante == 0:
                break

        # Paso 5: informar de dónde salió cada cantidad
        return salidas
    except OperationalError as error:
        if not any(texto in str(error).lower() for texto in ("locked", "busy")):
            raise
        raise ErrorDeNegocio("El inventario está siendo actualizado por otra operación. Reintenta.") from None
