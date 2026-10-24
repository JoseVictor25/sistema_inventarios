"""Modelos de compras: proveedores, compras y líneas de detalle.

Dependencias (§7.10):
    catalogo.Producto  ←──(FK)──  DetalleCompra  ──(FK)──▶  Compra  ──(FK)──▶  Proveedor ◆
    EntidadAuditable (core) ← Proveedor ◆, Compra ◆

Política on_delete:
    - Compra  → Proveedor: PROTECT  (proveedor con historial no se borra)
    - DetalleCompra → Compra: CASCADE (el detalle sigue a su cabecera)
    - DetalleCompra → Producto: PROTECT (producto con historial no se borra)
"""
import datetime
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalogo.models import Producto
from apps.core.models import EntidadAuditable
from apps.core.validators import validar_dinero


class Proveedor(EntidadAuditable):
    """Proveedor o fuente de compra: empresa o compra propia."""

    class TipoProveedor(models.TextChoices):
        EMPRESA = "EMPRESA", "Empresa"
        COMPRA_PROPIA = "COMPRA_PROPIA", "Compra propia"

    nombre = models.CharField(max_length=120, unique=True)
    tipo = models.CharField(max_length=20, choices=TipoProveedor)
    contacto = models.CharField(max_length=120, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    origen = models.CharField(
        max_length=80,
        blank=True,
        help_text="Ciudad o departamento de origen.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"

    def __str__(self):
        return self.nombre


class Compra(EntidadAuditable):
    """Registro de una compra a un proveedor.

    El total se calcula y guarda por el servicio al registrar la compra (§8.3).
    RN-19: las compras ya registradas no se editan; los errores se corrigen con ajuste.
    """

    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,
        related_name="compras",
    )
    fecha = models.DateField(default=datetime.date.today)
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[validar_dinero],
    )
    observacion = models.CharField(max_length=200, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="compras_registradas",
    )

    class Meta:
        ordering = ["-fecha"]
        constraints = [
            models.CheckConstraint(
                condition=Q(total__gte=0),
                name="compra_total_no_negativo",
            ),
        ]
        verbose_name = "compra"
        verbose_name_plural = "compras"

    def __str__(self):
        return f"Compra #{self.pk} — {self.proveedor} ({self.fecha})"


class DetalleCompra(models.Model):
    """Línea de una compra: producto, cantidad y costo unitario.

    CASCADE desde Compra: si se elimina la cabecera, sus líneas desaparecen también.
    Nota: el admin bloquea la eliminación de Compra para evitar esta cascada accidental.
    """

    compra = models.ForeignKey(
        Compra,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="detalles_compra",
    )
    cantidad_unidades = models.PositiveIntegerField()
    costo_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
    )

    class Meta:
        ordering = ["pk"]
        verbose_name = "detalle de compra"
        verbose_name_plural = "detalles de compra"
        constraints = [
            models.CheckConstraint(
                condition=Q(costo_unitario__gte=0),
                name="detalle_compra_costo_no_negativo",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0),
                name="detalle_compra_subtotal_no_negativo",
            ),
            models.CheckConstraint(
                condition=Q(cantidad_unidades__gte=1),
                name="detalle_compra_cantidad_minimo_1",
            ),
        ]

    def __str__(self):
        return f"{self.producto} × {self.cantidad_unidades}"
