"""Formularios y extractores de datos para ventas."""
from decimal import Decimal, InvalidOperation

from django import forms
from apps.core.exceptions import ErrorDeNegocio
from .models import MetodoPago


def leer_pagos(post_data, total_venta=None):
    """Extrae la lista de pagos desde request.POST admitiendo pago simple o mixto.

    Formato devuelto:
    [
        {"metodo_id": int, "monto": Decimal, "referencia": str},
        ...
    ]
    """
    pagos = []
    # Caso 1: Múltiples pagos (listas en POST)
    metodos_lista = post_data.getlist("metodo_id[]") or post_data.getlist("metodo_id")
    montos_lista = post_data.getlist("monto[]") or post_data.getlist("monto")
    refs_lista = post_data.getlist("referencia[]") or post_data.getlist("referencia")

    if len(metodos_lista) > 1 or len(montos_lista) > 1:
        metodos_vistos = set()
        for i, mid in enumerate(metodos_lista):
            if not mid:
                continue
            try:
                mid_int = int(mid)
            except (ValueError, TypeError):
                raise ErrorDeNegocio(f"Método de pago inválido: {mid}")
            if mid_int in metodos_vistos:
                raise ErrorDeNegocio("No se permite duplicar el mismo método de pago en una venta.")
            metodos_vistos.add(mid_int)

            monto_str = montos_lista[i] if i < len(montos_lista) else "0"
            ref_str = refs_lista[i] if i < len(refs_lista) else ""
            monto_limpio = str(monto_str).strip().replace(",", ".")
            try:
                monto = Decimal(monto_limpio)
            except (InvalidOperation, TypeError, ValueError):
                raise ErrorDeNegocio(f"El monto para el método #{mid} no es válido.")
            if monto <= Decimal("0.00"):
                raise ErrorDeNegocio("El monto de cada pago debe ser mayor que cero.")
            pagos.append({
                "metodo_id": mid_int,
                "monto": monto,
                "referencia": ref_str.strip(),
            })
        if not pagos:
            raise ErrorDeNegocio("Ingresa al menos un método de pago con monto mayor que cero.")
        return pagos

    # Caso 2: Pago único
    metodo_id = post_data.get("metodo_id")
    if not metodo_id:
        metodo = MetodoPago.objects.filter(activo=True).first()
        if not metodo:
            raise ErrorDeNegocio("No hay métodos de pago configurados.")
        metodo_id = metodo.pk
    try:
        metodo_id_int = int(metodo_id)
    except (ValueError, TypeError):
        raise ErrorDeNegocio("Identificador de método de pago inválido.")

    monto_raw = post_data.get("monto")
    if monto_raw:
        monto_limpio = str(monto_raw).strip().replace(",", ".")
        try:
            monto = Decimal(monto_limpio)
        except (InvalidOperation, TypeError, ValueError):
            raise ErrorDeNegocio("El monto ingresado no es válido.")
    elif total_venta is not None:
        monto = total_venta
    else:
        monto = Decimal("0.00")

    if monto <= Decimal("0.00"):
        raise ErrorDeNegocio("El monto de cada pago debe ser mayor que cero.")

    referencia = post_data.get("referencia", "").strip()
    pagos.append({
        "metodo_id": metodo_id_int,
        "monto": monto,
        "referencia": referencia,
    })
    return pagos
