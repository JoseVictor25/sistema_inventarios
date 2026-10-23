"""Validadores de formato compartidos por formularios y modelos."""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError


def validar_dinero(valor):
    """Exige Decimal finito, no negativo y con hasta dos decimales efectivos."""
    if not isinstance(valor, Decimal) or not valor.is_finite() or valor < 0:
        raise ValidationError("Ingresa un monto válido, mayor o igual a cero.")
    try:
        valido = valor == valor.quantize(Decimal("0.01"))
    except InvalidOperation:
        valido = False
    if not valido:
        raise ValidationError("El monto admite como máximo 2 decimales.")


def validar_cantidad(valor):
    """Exige una cantidad entera estrictamente positiva; no acepta booleanos."""
    if not isinstance(valor, int) or isinstance(valor, bool) or valor < 1:
        raise ValidationError("La cantidad debe ser un número entero mayor que cero.")
