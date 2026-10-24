"""Modelo de auditoría: registro inmutable de cambios sensibles.

RN-21: cambios de precio, ajustes de stock y cierres de caja quedan en LogAuditoria
con usuario, valor anterior y valor nuevo.

Este modelo es de solo lectura: el admin bloquea agregar, editar y borrar.
Las entradas las crean los servicios mediante auditoria/services.py (Fase 9).
"""
from django.conf import settings
from django.db import models


class LogAuditoria(models.Model):
    """Entrada de bitácora: quién hizo qué, sobre qué entidad y cuándo."""

    # SET_NULL: si el usuario se elimina, el registro histórico se conserva
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",  # sin acceso inverso: la bitácora no se muestra en el perfil
    )
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    accion = models.CharField(
        max_length=40,
        help_text='Ej.: "CAMBIO_PRECIO", "CIERRE_CAJA", "AJUSTE_INVENTARIO".',
    )
    entidad = models.CharField(
        max_length=60,
        help_text='Nombre del modelo afectado. Ej.: "Presentacion", "Caja".',
    )
    entidad_id = models.PositiveIntegerField(
        help_text="PK del objeto afectado. No es FK genérica para soportar cualquier app.",
    )
    valor_anterior = models.JSONField(null=True, blank=True)
    valor_nuevo = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"

    def __str__(self):
        return f"{self.accion} — {self.entidad} #{self.entidad_id} ({self.fecha:%Y-%m-%d %H:%M})"
