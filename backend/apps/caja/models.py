"""Modelos de caja: turnos de caja y movimientos de efectivo.

Dependencias (§7.10):
    EntidadAuditable (core) ← Caja ◆
    Caja ←──(FK)── MovimientoCaja

Política on_delete:
    - Caja → Usuario: PROTECT (el usuario que abrió/cerró no se borra)
    - MovimientoCaja → Caja: CASCADE (los movimientos son parte del turno)
    - MovimientoCaja → Usuario: PROTECT

Nota sobre monto_esperado():
    Usa apps.get_model("ventas", "Pago") para evitar la importación circular:
        caja.Caja → ventas.Venta → caja.Caja
    El método solo se puede llamar después de que Django haya cargado todos los modelos.

Reglas de negocio implementadas aquí (nivel modelo/BD):
    - RN-11: una sola caja ABIERTA por usuario → UniqueConstraint condicional
    - monto_inicial >= 0 → CheckConstraint
    - monto_caja > 0 → CheckConstraint en MovimientoCaja

Reglas que implementan los servicios (§8.4):
    - Validar monto_inicial con validar_dinero()
    - Verificar que caja esté ABIERTA antes de cerrar
    - Registrar en LogAuditoria al cerrar (RN-21)
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.models import EntidadAuditable
from apps.core.validators import validar_dinero


class Caja(EntidadAuditable):
    """Turno de caja: apertura, movimientos y cierre (RN-10 a RN-13)."""

    class EstadoCaja(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        CERRADA = "CERRADA", "Cerrada"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cajas",
        help_text="Usuario que abrió el turno.",
    )
    cerrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cajas_cerradas",
        help_text="Usuario que cerró el turno (puede ser el dueño).",
    )
    fecha_apertura = models.DateTimeField(default=timezone.now)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    monto_inicial = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
        help_text="Efectivo inicial en caja al abrir el turno.",
    )
    # null=True: se llena al cerrar; blank=True para pasar validación de formularios
    monto_contado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
        null=True,
        blank=True,
        help_text="Efectivo contado al cerrar el turno. Nulo mientras la caja esté abierta.",
    )
    estado = models.CharField(
        max_length=10,
        choices=EstadoCaja,
        default=EstadoCaja.ABIERTA,
    )
    turno = models.CharField(
        max_length=30,
        blank=True,
        help_text='Opcional. Ej.: "Mañana", "Tarde".',
    )
    observacion = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-fecha_apertura"]
        verbose_name = "turno de caja"
        verbose_name_plural = "turnos de caja"
        constraints = [
            models.CheckConstraint(
                condition=Q(monto_contado__gte=0) | Q(monto_contado__isnull=True),
                name="caja_monto_contado_no_negativo",
            ),
            # RN-11: un solo turno ABIERTO por usuario en cualquier momento
            models.UniqueConstraint(
                fields=["usuario"],
                condition=Q(estado="ABIERTA"),
                name="una_caja_abierta_por_usuario",
            ),
            models.CheckConstraint(
                condition=Q(monto_inicial__gte=0),
                name="caja_monto_inicial_no_negativo",
            ),
        ]

    def __str__(self):
        return f"Turno #{self.pk} — {self.usuario} ({self.estado})"

    def monto_esperado(self):
        """RN-12: monto_inicial + ventas_efectivo + ingresos − egresos.

        Solo se suman pagos cuyo MetodoPago.es_efectivo sea True.
        QR, Transferencia y otros métodos no se contabilizan como efectivo.
        """
        from django.apps import apps

        Pago = apps.get_model("ventas", "Pago")
        ventas_efectivo = (
            Pago.objects.filter(
                venta__caja=self,
                metodo__es_efectivo=True,
            ).aggregate(total=Sum("monto"))["total"]
            or Decimal("0")
        )
        ingresos = (
            self.movimientos.filter(tipo=MovimientoCaja.TipoMovimientoCaja.INGRESO)
            .aggregate(total=Sum("monto"))["total"]
            or Decimal("0")
        )
        egresos = (
            self.movimientos.filter(tipo=MovimientoCaja.TipoMovimientoCaja.EGRESO)
            .aggregate(total=Sum("monto"))["total"]
            or Decimal("0")
        )
        return self.monto_inicial + ventas_efectivo + ingresos - egresos

    def diferencia(self):
        """RN-13: efectivo contado − efectivo esperado.

        Positivo = sobra, negativo = falta, cero = cuadra.
        Devuelve None si aún no se ingresó monto_contado.
        """
        if self.monto_contado is None:
            return None
        return self.monto_contado - self.monto_esperado()


class MovimientoCaja(models.Model):
    """Ingreso o egreso de efectivo durante un turno de caja."""

    class TipoMovimientoCaja(models.TextChoices):
        INGRESO = "INGRESO", "Ingreso"
        EGRESO = "EGRESO", "Egreso"

    caja = models.ForeignKey(
        Caja,
        on_delete=models.CASCADE,
        related_name="movimientos",
    )
    tipo = models.CharField(max_length=10, choices=TipoMovimientoCaja)
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
    )
    concepto = models.CharField(max_length=120)
    fecha = models.DateTimeField(default=timezone.now)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimientos_caja",
    )

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "movimiento de caja"
        verbose_name_plural = "movimientos de caja"
        constraints = [
            models.CheckConstraint(
                condition=Q(monto__gt=0),
                name="movimiento_caja_monto_mayor_cero",
            ),
        ]

    def __str__(self):
        return f"{self.tipo} {self.monto} — {self.concepto}"


class OperacionCaja(models.Model):
    """Resultado persistente de una solicitud, reservado dentro de su transacción."""

    class Accion(models.TextChoices):
        ABRIR = "ABRIR", "Abrir"
        MOVIMIENTO = "MOVIMIENTO", "Movimiento"
        CERRAR = "CERRAR", "Cerrar"

    clave = models.UUIDField(unique=True, editable=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    accion = models.CharField(max_length=10, choices=Accion)
    huella = models.CharField(max_length=64, validators=[RegexValidator(r"^[0-9a-f]{64}$")])
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, null=True, blank=True)
    movimiento = models.ForeignKey(MovimientoCaja, on_delete=models.PROTECT, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-pk"]
        indexes = [models.Index(fields=["usuario", "-creado_en"], name="operacion_caja_usuario_fecha")]
        constraints = [
            models.CheckConstraint(condition=Q(accion__in=["ABRIR", "MOVIMIENTO", "CERRAR"]), name="operacion_caja_accion_valida"),
            models.CheckConstraint(condition=Q(accion="MOVIMIENTO") | Q(movimiento__isnull=True), name="operacion_caja_movimiento_tipo"),
        ]
