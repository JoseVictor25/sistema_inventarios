"""Modelos de ventas: métodos de pago, ventas, detalles, lotes descontados y pagos.

Dependencias (§7.10):
    caja.Caja           ←──(FK)──  Venta ◆
    catalogo.Presentacion ←──(FK)──  DetalleVenta
    inventario.Lote     ←──(FK)──  DetalleVentaLote
    ventas.Venta        ←──(FK)──  Pago  ──(FK)──▶  MetodoPago

Política on_delete:
    - Venta → Caja: PROTECT (la caja sigue existiendo)
    - Venta → Usuario: PROTECT
    - DetalleVenta → Venta: CASCADE (el detalle sigue a su cabecera)
    - DetalleVentaLote → DetalleVenta: CASCADE
    - DetalleVentaLote → Lote: PROTECT (historial del lote no se borra)
    - Pago → Venta: CASCADE
    - Pago → MetodoPago: PROTECT

Reglas implementadas a nivel BD:
    - total >= 0 (Venta)
    - cantidad_presentaciones >= 1 y unidades_totales >= 1 (DetalleVenta)
    - cantidad_unidades >= 1 (DetalleVentaLote)
    - monto > 0 (Pago)

Reglas que implementan los servicios (§8.1) — Fase 6:
    - RN-10: no vender sin caja abierta
    - RN-14: suma de pagos == total
    - RN-06/RN-07: FEFO y no vender lotes vencidos → descontar_stock_fefo()
    - RN-08: precio_aplicado se guarda de la presentación al momento de vender
    - RN-09: costo del lote para calcular ganancia → DetalleVentaLote
    Estas reglas NO tienen CheckConstraint en BD; se documentan aquí para referencia.
"""
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.caja.models import Caja
from apps.catalogo.models import Presentacion
from apps.core.models import EntidadAuditable
from apps.core.validators import validar_dinero
from apps.inventario.models import Lote


class MetodoPago(models.Model):
    """Método de pago aceptado. Los datos iniciales se crean con cargar_datos_iniciales."""

    nombre = models.CharField(max_length=40, unique=True)
    es_efectivo = models.BooleanField(
        default=False,
        help_text="True solo para Efectivo. Determina qué pagos cuentan en monto_esperado().",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "método de pago"
        verbose_name_plural = "métodos de pago"

    def __str__(self):
        return self.nombre


class Venta(EntidadAuditable):
    """Venta registrada durante un turno de caja (RN-10, RN-14, RN-15)."""

    caja = models.ForeignKey(
        Caja,
        on_delete=models.PROTECT,
        related_name="ventas",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ventas_realizadas",
    )
    fecha = models.DateTimeField(default=timezone.now)
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
    )

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "venta"
        verbose_name_plural = "ventas"
        constraints = [
            models.CheckConstraint(
                condition=Q(total__gte=0),
                name="venta_total_no_negativo",
            ),
        ]

    def __str__(self):
        return f"Venta #{self.pk} — {self.total}"


class DetalleVenta(models.Model):
    """Línea de una venta: presentación elegida, cantidad y precio aplicado.

    precio_aplicado se guarda al momento de vender para preservar el histórico (RN-08).
    La consistencia subtotal = precio_aplicado × cantidad_presentaciones la garantiza
    el servicio registrar_venta() (Fase 6), no una restricción de BD.
    """

    venta = models.ForeignKey(
        Venta,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    presentacion = models.ForeignKey(
        Presentacion,
        on_delete=models.PROTECT,
        related_name="detalles_venta",
    )
    cantidad_presentaciones = models.PositiveIntegerField()
    unidades_totales = models.PositiveIntegerField(
        help_text="cantidad_presentaciones × unidades_equivalentes (calculado al vender).",
    )
    precio_aplicado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
        help_text="Precio de la presentación al momento de la venta (RN-08).",
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
    )

    class Meta:
        ordering = ["pk"]
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"
        constraints = [
            models.CheckConstraint(
                condition=Q(precio_aplicado__gte=0),
                name="detalle_venta_precio_no_negativo",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0),
                name="detalle_venta_subtotal_no_negativo",
            ),
            models.CheckConstraint(
                condition=Q(cantidad_presentaciones__gte=1),
                name="detalle_venta_cantidad_presentaciones_minimo_1",
            ),
            models.CheckConstraint(
                condition=Q(unidades_totales__gte=1),
                name="detalle_venta_unidades_totales_minimo_1",
            ),
        ]

    def __str__(self):
        return f"{self.presentacion} × {self.cantidad_presentaciones}"


class DetalleVentaLote(models.Model):
    """Registro de qué lote aportó unidades para una línea de venta (RN-09).

    Permite calcular el costo real de lo vendido y la ganancia por lote.
    CASCADE desde DetalleVenta: si se borra el detalle (con la venta), esto desaparece.
    PROTECT desde Lote: no se puede borrar un lote con historial de ventas.
    """

    detalle_venta = models.ForeignKey(
        DetalleVenta,
        on_delete=models.CASCADE,
        related_name="salidas_lote",
    )
    lote = models.ForeignKey(
        Lote,
        on_delete=models.PROTECT,
        related_name="salidas_venta",
    )
    cantidad_unidades = models.PositiveIntegerField()

    class Meta:
        ordering = ["pk"]
        verbose_name = "detalle de venta por lote"
        verbose_name_plural = "detalles de venta por lote"
        constraints = [
            models.CheckConstraint(
                condition=Q(cantidad_unidades__gte=1),
                name="detalle_venta_lote_cantidad_minimo_1",
            ),
        ]

    def __str__(self):
        return f"{self.lote} × {self.cantidad_unidades} u."


class Pago(models.Model):
    """Pago parcial o total de una venta (RN-14).

    monto guarda lo aplicado al total; el vuelto se calcula en pantalla y no se guarda.
    CASCADE desde Venta: si se borra la venta, sus pagos desaparecen también.
    PROTECT desde MetodoPago: el método de pago no se puede borrar si tiene historial.
    """

    venta = models.ForeignKey(
        Venta,
        on_delete=models.CASCADE,
        related_name="pagos",
    )
    metodo = models.ForeignKey(
        MetodoPago,
        on_delete=models.PROTECT,
        related_name="pagos",
    )
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
        help_text="Monto aplicado al total (sin vuelto — RN-14).",
    )
    referencia = models.CharField(
        max_length=60,
        blank=True,
        help_text="Número de referencia QR o transferencia.",
    )

    class Meta:
        ordering = ["pk"]
        verbose_name = "pago"
        verbose_name_plural = "pagos"
        constraints = [
            models.CheckConstraint(
                condition=Q(monto__gt=0),
                name="pago_monto_mayor_cero",
            ),
        ]

    def __str__(self):
        return f"{self.metodo} {self.monto}"


class OperacionVenta(models.Model):
    """Resultado persistente de una solicitud de venta, reservado dentro de su transacción."""

    clave = models.UUIDField(unique=True, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operaciones_venta",
    )
    huella = models.CharField(
        max_length=64,
        validators=[RegexValidator(r"^[0-9a-f]{64}$")],
    )
    venta = models.ForeignKey(
        Venta,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operaciones",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-pk"]
        verbose_name = "operación de venta"
        verbose_name_plural = "operaciones de venta"
        indexes = [
            models.Index(fields=["usuario", "-creado_en"], name="operacion_venta_usuario_fecha"),
        ]

    def __str__(self):
        return f"Operación Venta {self.clave} — {self.usuario}"
