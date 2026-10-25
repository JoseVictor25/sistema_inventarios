"""Modelos del catálogo: categorías, productos, presentaciones y atributos.

Dependencias (§7.10):
    EntidadAuditable (core) ← Producto ◆
                             ← Presentacion ◆
    Categoria  ←──(FK)──  Producto  ←──(FK)──  AtributoProducto
                                               ← Presentacion
"""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum

from apps.core.models import EntidadAuditable
from apps.core.validators import validar_dinero


class Categoria(models.Model):
    """Categoría jerárquica de productos (árbol, sin ciclos — RN-18)."""

    nombre = models.CharField(max_length=80)
    padre = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="hijos",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        constraints = [
            # Nombre único dentro del mismo padre (incluye padre=NULL vs padre=X)
            models.UniqueConstraint(
                fields=["padre", "nombre"],
                name="categoria_nombre_unico_por_padre",
            ),
            # Nombre único entre las categorías raíz (padre IS NULL)
            models.UniqueConstraint(
                fields=["nombre"],
                condition=Q(padre__isnull=True),
                name="categoria_raiz_nombre_unico",
            ),
        ]

    def __str__(self):
        return self.nombre

    def clean(self):
        """RN-18: detecta ciclos en la jerarquía de categorías."""
        from django.core.exceptions import ValidationError

        visitados = {self.pk} if self.pk is not None else set()
        ancestro_id = self.padre_id
        while ancestro_id is not None:
            if ancestro_id in visitados:
                raise ValidationError(
                    "Una categoría no puede ser su propia ancestra (RN-18)."
                )
            visitados.add(ancestro_id)
            # Consultar el estado persistido, no relaciones cacheadas de instancias.
            ancestro_id = Categoria.objects.filter(pk=ancestro_id).values_list("padre_id", flat=True).first()


class Producto(EntidadAuditable):
    """Producto del catálogo con código único y stock mínimo configurable (§7)."""

    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name="productos",
    )
    stock_minimo = models.PositiveIntegerField(
        default=settings.STOCK_MINIMO_DEFECTO,
        validators=[MinValueValidator(0)],
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "producto"
        verbose_name_plural = "productos"

    def __str__(self):
        return self.nombre

    @property
    def stock_actual(self):
        """Suma de cantidad_actual de todos los lotes del producto (RN-01).

        Se calcula en tiempo real; las vistas lo optimizan con annotate() cuando
        necesitan ordenar o filtrar por stock.
        """
        resultado = self.lotes.aggregate(total=Sum("cantidad_actual"))
        return resultado["total"] or 0


class AtributoProducto(models.Model):
    """Atributo clave-valor asociado a un producto (origen, aroma, etc.)."""

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="atributos",
    )
    nombre = models.CharField(max_length=60)
    valor = models.CharField(max_length=120)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "atributo de producto"
        verbose_name_plural = "atributos de producto"
        constraints = [
            models.UniqueConstraint(
                fields=["producto", "nombre"],
                name="atributo_nombre_unico_por_producto",
            ),
        ]

    def __str__(self):
        return f"{self.nombre}: {self.valor}"


class Presentacion(EntidadAuditable):
    """Presentación de venta de un producto (unidad, docena, caja…) — RN-02, RN-03."""

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="presentaciones",
    )
    nombre = models.CharField(max_length=40)
    unidades_equivalentes = models.PositiveIntegerField(
        help_text="Cuántas unidades representa esta presentación (≥ 1)."
    )
    precio_venta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[validar_dinero],
    )
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "presentación"
        verbose_name_plural = "presentaciones"
        constraints = [
            models.CheckConstraint(
                condition=Q(precio_venta__gte=0),
                name="presentacion_precio_no_negativo",
            ),
            # RN-02: nombre no repetido dentro del mismo producto
            models.UniqueConstraint(
                fields=["producto", "nombre"],
                name="presentacion_nombre_unico_por_producto",
            ),
            # RN-02/RN-04: mínimo 1 unidad equivalente (nivel BD)
            models.CheckConstraint(
                condition=Q(unidades_equivalentes__gte=1),
                name="presentacion_unidades_minimo_1",
            ),
        ]

    def __str__(self):
        return f"{self.producto} — {self.nombre}"
