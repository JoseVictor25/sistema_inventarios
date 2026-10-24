"""Modelos del inventario: lotes y movimientos de stock.

Dependencias (§7.10):
    catalogo.Producto    ←──(FK)──  Lote  ──(OneToOne)──▶  compras.DetalleCompra
    inventario.Lote      ←──(FK)──  MovimientoInventario

Política on_delete:
    - Lote → Producto: PROTECT (producto con lotes no se borra)
    - Lote → DetalleCompra: PROTECT (la compra no se borra si tiene lote)
    - MovimientoInventario → Lote: PROTECT (historial inmutable)

Restricciones a nivel BD (§7.10):
    - cantidad_inicial >= 1
    - cantidad_actual <= cantidad_inicial   ← referencia a otra columna con F()
    - movimiento.cantidad != 0

Restricciones que requieren servicio transaccional (documentadas aquí, §6.1):
    - cantidad_actual >= 0  ← garantizado por PositiveIntegerField (no negativo)
    - FEFO: descontar del lote que vence primero (RN-06) → services.py
    - No vender lotes vencidos (RN-07) → services.py
    - Consistencia entre movimiento.tipo y el signo de cantidad → services.py
"""
from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.catalogo.models import Producto
from apps.compras.models import DetalleCompra
from apps.core.validators import validar_dinero


class Lote(models.Model):
    """Lote de unidades de un producto con costo, cantidad y vencimiento — RN-05."""

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="lotes",
    )
    detalle_compra = models.OneToOneField(
        DetalleCompra,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lote",
        help_text="Línea de compra que originó este lote. Nulo en lotes de ajuste.",
    )
    codigo_lote = models.CharField(
        max_length=30,
        unique=True,
        help_text="Formato sugerido: L-AAAA-NNNN (generado por el servicio).",
    )
    fecha_vencimiento = models.DateField(
        null=True,
        blank=True,
        help_text="Vacío si el producto no vence.",
    )
    cantidad_inicial = models.PositiveIntegerField(
        help_text="Unidades al registrar la compra (>= 1)."
    )
    cantidad_actual = models.PositiveIntegerField(
        help_text="Unidades disponibles (0 ≤ cantidad_actual ≤ cantidad_inicial)."
    )
    costo_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
    )

    class Meta:
        ordering = ["fecha_vencimiento", "id"]
        verbose_name = "lote"
        verbose_name_plural = "lotes"
        constraints = [
            models.CheckConstraint(
                condition=Q(costo_unitario__gte=0),
                name="lote_costo_no_negativo",
            ),
            # cantidad_inicial mínimo 1 (PositiveIntegerField permite 0)
            models.CheckConstraint(
                condition=Q(cantidad_inicial__gte=1),
                name="lote_cantidad_inicial_minimo_1",
            ),
            # cantidad_actual no puede superar cantidad_inicial (FK a otra columna)
            models.CheckConstraint(
                condition=Q(cantidad_actual__lte=F("cantidad_inicial")),
                name="lote_cantidad_actual_no_supera_inicial",
            ),
        ]

    def __str__(self):
        return self.codigo_lote


class MovimientoInventario(models.Model):
    """Registro inmutable de un movimiento de stock en un lote.

    RN-19: solo se crean, nunca se editan ni se borran.
    El admin bloquea la edición y el borrado (inventario/admin.py).

    Signo de cantidad según tipo (§7.10):
        ENTRADA  → cantidad > 0
        SALIDA   → cantidad < 0
        MERMA    → cantidad < 0
        AJUSTE   → cualquier signo distinto de 0
    El servicio es responsable de respetar este convenio; la BD solo exige ≠ 0.
    """

    class TipoMovimiento(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SALIDA = "SALIDA", "Salida"
        AJUSTE = "AJUSTE", "Ajuste"
        MERMA = "MERMA", "Merma"

    lote = models.ForeignKey(
        Lote,
        on_delete=models.PROTECT,
        related_name="movimientos",
    )
    tipo = models.CharField(max_length=10, choices=TipoMovimiento)
    # IntegerField con signo: positivo (ENTRADA), negativo (SALIDA/MERMA), distinto de 0 (AJUSTE)
    cantidad = models.IntegerField()
    fecha = models.DateTimeField(auto_now_add=True)
    motivo = models.CharField(
        max_length=200,
        blank=True,
        help_text='Ej.: "Venta #123", "Producto dañado".',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimientos_inventario",
    )

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "movimiento de inventario"
        verbose_name_plural = "movimientos de inventario"
        constraints = [
            # La BD exige que cantidad sea distinta de cero; el signo lo controla el servicio
            models.CheckConstraint(
                condition=~Q(cantidad=0),
                name="movimiento_inventario_cantidad_distinta_cero",
            ),
        ]

    def __str__(self):
        return f"{self.tipo} {self.cantidad:+d} — {self.lote}"
