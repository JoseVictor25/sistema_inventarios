"""Pruebas de modelos para la app inventario: Lote y MovimientoInventario."""
from decimal import Decimal

from django.db.models import ProtectedError
from django.db.utils import IntegrityError
from django.test import TestCase

from apps.catalogo.models import Categoria, Producto
from apps.inventario.models import Lote, MovimientoInventario
from apps.usuarios.models import Usuario


class InventarioModelTest(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(username="almacenero", password="pwd")
        self.cat = Categoria.objects.create(nombre="Aceites Esenciales")
        self.prod = Producto.objects.create(
            codigo="AE-01",
            nombre="Aceite de Lavanda",
            categoria=self.cat,
            creado_por=self.user,
            modificado_por=self.user,
        )

    def test_lote_codigo_unico(self):
        Lote.objects.create(
            producto=self.prod,
            codigo_lote="L-2026-0010",
            cantidad_inicial=10,
            cantidad_actual=10,
            costo_unitario=Decimal("25.00"),
        )
        with self.assertRaises(IntegrityError):
            Lote.objects.create(
                producto=self.prod,
                codigo_lote="L-2026-0010",
                cantidad_inicial=5,
                cantidad_actual=5,
                costo_unitario=Decimal("25.00"),
            )

    def test_lote_cantidad_inicial_minimo_uno_constraint(self):
        with self.assertRaises(IntegrityError):
            Lote.objects.create(
                producto=self.prod,
                codigo_lote="L-2026-0011",
                cantidad_inicial=0,
                cantidad_actual=0,
                costo_unitario=Decimal("15.00"),
            )

    def test_lote_cantidad_actual_no_supera_inicial_constraint(self):
        # cantidad_actual (15) > cantidad_inicial (10) violaría CheckConstraint
        with self.assertRaises(IntegrityError):
            Lote.objects.create(
                producto=self.prod,
                codigo_lote="L-2026-0012",
                cantidad_inicial=10,
                cantidad_actual=15,
                costo_unitario=Decimal("15.00"),
            )

    def test_movimiento_inventario_cantidad_distinta_cero_constraint(self):
        lote = Lote.objects.create(
            producto=self.prod,
            codigo_lote="L-2026-0013",
            cantidad_inicial=20,
            cantidad_actual=20,
            costo_unitario=Decimal("10.00"),
        )
        with self.assertRaises(IntegrityError):
            MovimientoInventario.objects.create(
                lote=lote,
                tipo=MovimientoInventario.TipoMovimiento.AJUSTE,
                cantidad=0,
                motivo="Ajuste cero inválido",
                usuario=self.user,
            )

    def test_protect_en_lote_con_movimientos(self):
        lote = Lote.objects.create(
            producto=self.prod,
            codigo_lote="L-2026-0014",
            cantidad_inicial=20,
            cantidad_actual=20,
            costo_unitario=Decimal("10.00"),
        )
        MovimientoInventario.objects.create(
            lote=lote,
            tipo=MovimientoInventario.TipoMovimiento.ENTRADA,
            cantidad=20,
            motivo="Entrada inicial",
            usuario=self.user,
        )
        with self.assertRaises(ProtectedError):
            lote.delete()
